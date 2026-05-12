# -*- coding: utf-8 -*-
"""三层漏斗顶层调度。

入口：
    run(db, universe, config, as_of_date, user_id) -> run_id

流程：
1. 在 screen_run 表创建一条 running 记录
2. 对每家 company 串行跑 Q0 → Q-Layer → R-Layer → V-Layer → status_resolver
3. 写 screen_result 一行
4. 完成后更新 screen_run.status = completed + 汇总计数
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.screen_result import ScreenResult
from backend.models.screen_run import ScreenRun

from backend.screening.config import ScreenConfig
from backend.screening.exclusion import evaluate_q0
from backend.screening.q_layer import evaluate_q_layer
from backend.screening.r_layer import evaluate_r_layer
from backend.screening.status_resolver import resolve_status
from backend.screening.v_layer import evaluate_v_layer


log = logging.getLogger(__name__)


def _build_metrics_snapshot(q_res: dict, r_res: dict, v_res: dict) -> dict:
    """合并三层 metrics 形成 screen_result.metrics_snapshot。"""
    snap = {}
    snap.update(q_res.get("metrics") or {})
    snap.update(r_res.get("metrics") or {})
    snap.update(v_res.get("metrics") or {})
    return {k: v for k, v in snap.items() if v is not None}


def _evaluate_one_company(
    db: Session,
    company: Company,
    asof_date: date,
    config: ScreenConfig,
    *,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
) -> dict:
    """对单家公司跑完整漏斗，返回 screen_result 行参数（未含 run_id）。"""
    reason_codes: list[str] = []

    # ===== Q0 =====
    q0_code = evaluate_q0(company)
    if q0_code is not None:
        return {
            "company_id": company.company_id,
            "status": "Rejected",
            "q_passed": False,
            "q_strong_track": False,
            "r_action": None,
            "v_state": None,
            "reason_codes": [q0_code],
            "metrics_snapshot": {},
            "ai_result_id": None,
        }

    # ===== Q-Layer =====
    q_res = evaluate_q_layer(db, company, asof_date, config)
    reason_codes.extend(q_res["reason_codes"])

    # ===== R-Layer =====
    # 即使 Q 不通过也跑 R/V，便于详情页展示完整信号
    r_res = evaluate_r_layer(
        db, company.company_id, asof_date, config,
        user_id=user_id, run_id=run_id,
    )
    reason_codes.extend(r_res["reason_codes"])

    # ===== V-Layer =====
    v_res = evaluate_v_layer(
        db, company.company_id, asof_date, config,
        q_passed=q_res["q_passed"],
        q_strong_track=q_res["q_strong_track"],
    )
    reason_codes.extend(v_res["reason_codes"])

    # ===== 状态裁决 =====
    status = resolve_status(q_res, r_res, v_res)

    return {
        "company_id": company.company_id,
        "status": status,
        "q_passed": q_res["q_passed"],
        "q_strong_track": q_res["q_strong_track"],
        "r_action": r_res["r_action"],
        "v_state": v_res["v_state"],
        "reason_codes": reason_codes,
        "metrics_snapshot": _build_metrics_snapshot(q_res, r_res, v_res),
        "ai_result_id": r_res.get("ai_result_id"),
    }


def run(
    universe: list[str],
    config: ScreenConfig,
    as_of_date: date,
    user_id: int,
    *,
    universe_name: str = "custom",
    market: str = "MIXED",
) -> int:
    """启动一次筛选。同步执行（M5 异步化时改为 BackgroundTasks）。

    返回 run_id。
    """
    db = SessionLocal()
    try:
        # 1. 建 screen_run
        config_snapshot = asdict(config) if is_dataclass(config) else dict(config)
        sr = ScreenRun(
            user_id=user_id,
            universe_name=universe_name,
            universe_snapshot=list(universe),
            market=market,
            as_of_date=as_of_date,
            config_snapshot=config_snapshot,
            status="running",
            total_count=len(universe),
        )
        db.add(sr)
        db.flush()
        run_id = sr.run_id
        db.commit()

        # 2. 逐家执行
        passed = 0
        rejected = 0
        review = 0
        errors = 0

        for cid in universe:
            company = db.get(Company, cid)
            if company is None:
                continue
            try:
                params = _evaluate_one_company(
                    db, company, as_of_date, config,
                    user_id=user_id, run_id=run_id,
                )
                status = params["status"]
                if status == "Rejected":
                    rejected += 1
                elif status == "Review":
                    review += 1
                else:
                    passed += 1
                row = ScreenResult(run_id=run_id, **params)
                db.add(row)
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors += 1
                log.exception("screening failed for %s: %s", cid, e)
        db.commit()

        # 3. 更新 run 状态 + 汇总
        db.execute(
            update(ScreenRun)
            .where(ScreenRun.run_id == run_id)
            .values(
                status="completed" if errors == 0 else "failed",
                finished_at=datetime.now(),
                passed_count=passed,
                rejected_count=rejected,
                review_count=review,
                error_msg=f"{errors} errors" if errors else None,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def run_default_us(user_id: int = 1, as_of_date: Optional[date] = None) -> int:
    """便捷入口：跑全美股池，默认标准配置。"""
    from backend.screening.config import PRESET_STANDARD
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Company.company_id).where(Company.market == "US")
        ).all()
    finally:
        db.close()
    cids = [r[0] for r in rows]
    return run(cids, PRESET_STANDARD, as_of_date or date(2024, 12, 31), user_id,
               universe_name="us_default", market="US")


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from backend.screening.config import PRESET_STRICT, PRESET_STANDARD, PRESET_LOOSE

    parser = argparse.ArgumentParser(description="V2 三层漏斗筛选")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--as-of", default="2024-12-31")
    parser.add_argument("--market", choices=["US", "CN_A", "ALL"], default="US")
    parser.add_argument("--preset", choices=["strict", "standard", "loose"], default="standard")
    args = parser.parse_args()

    preset_map = {"strict": PRESET_STRICT, "standard": PRESET_STANDARD, "loose": PRESET_LOOSE}
    cfg = preset_map[args.preset]

    db = SessionLocal()
    try:
        q = select(Company.company_id)
        if args.market != "ALL":
            q = q.where(Company.market == args.market)
        cids = [r[0] for r in db.execute(q).all()]
    finally:
        db.close()

    asof = date.fromisoformat(args.as_of)
    run_id = run(cids, cfg, asof, args.user_id,
                 universe_name=f"{args.market}_{args.preset}",
                 market=args.market if args.market != "ALL" else "MIXED")

    db = SessionLocal()
    try:
        sr = db.get(ScreenRun, run_id)
        print(json.dumps({
            "run_id": run_id,
            "status": sr.status,
            "total": sr.total_count,
            "passed": sr.passed_count,
            "rejected": sr.rejected_count,
            "review": sr.review_count,
        }, indent=2))
    finally:
        db.close()
