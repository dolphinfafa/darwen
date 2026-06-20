# -*- coding: utf-8 -*-
"""三层漏斗引擎 v2：ROCE → 稳健性 → 风险性，分层执行 + 人工 gate。

与旧 funnel.py（Q/R/V + 估值）的区别：
- 去掉估值层；三层为 ROCE(规则) → 稳健性(规则+AI) → 风险性(AI)。
- 分层执行：每层跑完默认停在 awaiting_review 等人工放行/剔除，再 advance 下一层
  （run.auto_advance=True 时三层连跑）。
- 存活集语义：screen_result.rejected_at_layer IS NULL 即"当前存活/最终入选"；
  某层把不通过的公司标记 rejected_at_layer=该层。人工 force_pass 复活(置 NULL)、
  force_reject 出局(置当前层)。每层只处理存活集，计数自然守恒。

阶段说明：稳健层目前仅实现"无负债有充裕现金流"这一条可量化规则，其余 5 条稳健原则
与整个风险层标记为 pending_ai，由阶段 3 接入 AI 判定后真正过滤（pending 不影响存活）。
"""
from __future__ import annotations

import logging
from dataclasses import fields as dataclass_fields
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
from backend.screening.r_layer import _latest_section

log = logging.getLogger(__name__)

# 漏斗层顺序
LAYERS: tuple[str, ...] = ("roce", "sturdiness", "risk")
_NEXT: dict[str, str] = {"roce": "sturdiness", "sturdiness": "risk", "risk": "done"}

# 稳健层 reason codes（阶段2 规则部分）
STURDINESS_PASS = "STURDINESS_PASS"
STURDINESS_HIGH_DEBT = "STURDINESS_HIGH_DEBT"
STURDINESS_WEAK_COVERAGE = "STURDINESS_WEAK_COVERAGE"
STURDINESS_NEGATIVE_FCF = "STURDINESS_NEGATIVE_FCF"
# 风险层占位（阶段3 接 AI）
RISK_PENDING_AI = "RISK_PENDING_AI"

# 稳健性 6 原则 key（前端展示用；阶段2 仅第 1 条有规则判定）
_STURDINESS_PRINCIPLES = (
    "no_debt_strong_cashflow",   # 无负债、有充裕现金流（规则）
    "diversified_customers",     # 多元化客户（AI）
    "high_moat",                 # 竞争壁垒高（ROCE 代理 + AI）
    "diversified_suppliers",     # 多元化供应商（AI）
    "stable_management",         # 稳定管理团队（AI）
    "slow_changing_industry",   # 行业变化慢（AI）
)


# ---------------- 配置/状态 helpers ----------------

def _config_from_run(run: ScreenRun) -> ScreenConfig:
    """从 run.config_snapshot 重建 ScreenConfig（仅取匹配字段，缺失用默认）。"""
    snap = dict(run.config_snapshot or {})
    valid = {f.name for f in dataclass_fields(ScreenConfig)}
    return ScreenConfig(**{k: v for k, v in snap.items() if k in valid})


def _set_run(db: Session, run_id: int, **values) -> None:
    """独立 UPDATE 刷新 screen_run 字段并 commit（避免与逐行 add 冲突）。"""
    db.execute(update(ScreenRun).where(ScreenRun.run_id == run_id).values(**values))
    db.commit()


def _recount(db: Session, run_id: int) -> tuple[int, int]:
    """重新统计存活/出局并写回 run。返回 (alive, rejected)。"""
    rows = db.execute(
        select(ScreenResult.rejected_at_layer).where(ScreenResult.run_id == run_id)
    ).all()
    alive = sum(1 for r in rows if r.rejected_at_layer is None)
    rejected = sum(1 for r in rows if r.rejected_at_layer is not None)
    _set_run(db, run_id, passed_count=alive, rejected_count=rejected)
    return alive, rejected


# ---------------- 各层评估（纯判定，返回 (alive, layer_result, status_hint)）----------------

def _eval_roce(db: Session, company: Company, asof: date, config: ScreenConfig) -> tuple[bool, dict, str]:
    """ROCE 层：Q0 排除 + ROCE 门槛（按 config.roce_lookback_years）。"""
    q0 = evaluate_q0(company)
    if q0 is not None:
        return False, {"passed": False, "reason_codes": [q0], "metrics": {}}, "Rejected"

    q = evaluate_q_layer(db, company, asof, config)
    passed = bool(q["q_passed"])
    result = {
        "passed": passed,
        "reason_codes": list(q["reason_codes"]),
        "metrics": {k: v for k, v in (q.get("metrics") or {}).items() if v is not None},
        "q_strong_track": bool(q["q_strong_track"]),
    }
    # Q5（负资本/缺失）属"需人工覆核"，状态标 Review 但仍按未通过过滤
    status = "Review" if any(c.startswith("Q5") for c in q["reason_codes"]) else (
        "HighConviction" if passed else "Rejected"
    )
    return passed, result, status


# AI 标签 → 稳健性原则 key（AI 判定后更新 principle 状态）
_STURDINESS_LABEL_TO_PRINCIPLE = {
    "customer_concentration_risk": "diversified_customers",
    "supplier_concentration_risk": "diversified_suppliers",
    "disruption_risk": "slow_changing_industry",
    "management_instability": "stable_management",
}


def _run_layer_ai(db: Session, company_id: str, asof: date, config: ScreenConfig,
                  user_id: Optional[int], run_id: Optional[int], layer: str):
    """调某层 AI 判定。返回 (ai_action, ai_result_id, ai_codes, labels)；
    未启用 AI / 未绑 key / 调用降级 → (None, None, [], [])。"""
    if not (config.ai_enabled_for(layer) and user_id is not None):
        return None, None, [], []
    from backend.ai.orchestrator import analyze_layer, AIResult
    # 用独立 session 调 AI：AI 内部的 commit/异常不污染漏斗主 session（否则整层 run_from 会抛错卡 running）
    ai_db = SessionLocal()
    try:
        outcome = analyze_layer(
            ai_db, company_id=company_id, asof_date=asof, user_id=user_id,
            run_id=run_id, layer=layer, rule_triggered={},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("AI %s layer failed for %s: %s", layer, company_id, e)
        return None, None, [], []
    finally:
        ai_db.close()
    if not isinstance(outcome, AIResult):
        return None, None, [], []  # RuleOnly 降级
    codes = [
        f"AI_{lbl.label.upper()}" + ("_HIGH" if lbl.severity == "high" else "")
        for lbl in outcome.output.labels
    ]
    return outcome.overall_action, outcome.ai_result_id, codes, outcome.output.labels


def _eval_sturdiness(db: Session, company_id: str, asof: date, config: ScreenConfig,
                     user_id: Optional[int], run_id: Optional[int]) -> tuple[bool, dict]:
    """稳健层：'无负债有充裕现金流' 规则 + 其余 4 条 AI 判定（启用 AI 时）。"""
    reason_codes: list[str] = []
    metrics: dict[str, float] = {}
    nd_ebit = _latest_section(db, company_id, "net_debt_ebit", "leverage_v1", asof)
    int_cov = _latest_section(db, company_id, "interest_coverage", "leverage_v1", asof)
    fcf_neg = _latest_section(db, company_id, "fcf_neg_5y_years", "cash_quality_v1", asof)
    rule_fail = False
    if nd_ebit is not None:
        metrics["net_debt_ebit"] = nd_ebit
        if nd_ebit > config.r1_net_debt_ebit_max:
            reason_codes.append(STURDINESS_HIGH_DEBT); rule_fail = True
    if int_cov is not None:
        metrics["interest_coverage"] = int_cov
        if int_cov < config.r1_interest_coverage_min:
            reason_codes.append(STURDINESS_WEAK_COVERAGE); rule_fail = True
    if fcf_neg is not None:
        metrics["fcf_neg_5y_years"] = fcf_neg
        if fcf_neg > config.r2_fcf_neg_5y_max:
            reason_codes.append(STURDINESS_NEGATIVE_FCF); rule_fail = True

    principles = {
        "no_debt_strong_cashflow": {"status": "fail" if rule_fail else "pass",
                                    "method": "rule", "metrics": metrics},
    }

    ai_action, ai_id, ai_codes, labels = _run_layer_ai(
        db, company_id, asof, config, user_id, run_id, "sturdiness")
    reason_codes.extend(ai_codes)
    pending = ai_action is None
    if pending:
        for p in _STURDINESS_PRINCIPLES[1:]:
            principles[p] = {"status": "pending_ai", "method": "ai"}
    else:
        flagged: dict[str, dict] = {}
        for lbl in labels:
            pk = _STURDINESS_LABEL_TO_PRINCIPLE.get(lbl.label)
            if pk:
                flagged[pk] = {"status": "fail", "method": "ai", "severity": lbl.severity,
                               "reason": lbl.short_reason, "evidence_doc_ids": lbl.evidence_doc_ids}
        for p in _STURDINESS_PRINCIPLES[1:]:
            principles[p] = flagged.get(p, {"status": "pass", "method": "ai"})

    passed = (not rule_fail) and (ai_action != "REJECT")
    if passed and not reason_codes:
        reason_codes.append(STURDINESS_PASS)
    return passed, {
        "passed": passed, "reason_codes": reason_codes, "metrics": metrics,
        "principles": principles, "pending_ai": pending,
        "ai_result_id": ai_id, "ai_action": ai_action,
    }


def _eval_risk(db: Session, company_id: str, asof: date, config: ScreenConfig,
               user_id: Optional[int], run_id: Optional[int]) -> tuple[bool, dict]:
    """风险层：AI 判定 5 条风险原则（启用 AI 时）；未启用→占位放行待人工。"""
    ai_action, ai_id, ai_codes, labels = _run_layer_ai(
        db, company_id, asof, config, user_id, run_id, "risk")
    if ai_action is None:
        return True, {"passed": True, "reason_codes": [RISK_PENDING_AI], "metrics": {},
                      "pending_ai": True, "ai_result_id": None, "ai_action": None}
    passed = ai_action != "REJECT"
    return passed, {"passed": passed, "reason_codes": ai_codes, "metrics": {},
                    "pending_ai": False, "ai_result_id": ai_id, "ai_action": ai_action}


_LAYER_EVAL = {
    "sturdiness": _eval_sturdiness,
    "risk": _eval_risk,
}


# ---------------- 分层执行 ----------------

def _alive_company_ids(db: Session, run_id: int) -> list[str]:
    """当前存活集：rejected_at_layer IS NULL 的 result（按 result_id 稳定排序）。"""
    rows = db.execute(
        select(ScreenResult.company_id)
        .where(ScreenResult.run_id == run_id, ScreenResult.rejected_at_layer.is_(None))
        .order_by(ScreenResult.result_id)
    ).all()
    return [r.company_id for r in rows]


def _run_roce_layer(db: Session, run: ScreenRun, config: ScreenConfig) -> None:
    """ROCE 层：对全 universe 建 screen_result 行。"""
    universe = list(run.universe_snapshot or [])
    _set_run(db, run.run_id, current_layer="roce", layer_status="running",
             progress_count=0, total_count=len(universe), current_company_name=None)

    for idx, cid in enumerate(universe, 1):
        company = db.get(Company, cid)
        if company is None:
            _set_run(db, run.run_id, progress_count=idx)
            continue
        try:
            alive, layer_res, status = _eval_roce(db, company, run.as_of_date, config)
            row = ScreenResult(
                run_id=run.run_id,
                company_id=cid,
                status=status,
                q_passed=layer_res.get("passed", False),
                q_strong_track=layer_res.get("q_strong_track", False),
                reason_codes=list(layer_res.get("reason_codes") or []),
                metrics_snapshot=dict(layer_res.get("metrics") or {}),
                layer_results={"roce": layer_res},
                rejected_at_layer=None if alive else "roce",
            )
            db.add(row)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.exception("roce layer failed for %s: %s", cid, e)
        _set_run(db, run.run_id, progress_count=idx, current_company_name=company.name)

    _recount(db, run.run_id)


def _run_ai_layer(db: Session, run: ScreenRun, config: ScreenConfig, layer: str) -> None:
    """稳健层 / 风险层：仅处理存活集，更新各行。"""
    eval_fn = _LAYER_EVAL[layer]
    company_ids = _alive_company_ids(db, run.run_id)
    _set_run(db, run.run_id, current_layer=layer, layer_status="running",
             progress_count=0, current_company_name=None)

    for idx, cid in enumerate(company_ids, 1):
        sr = db.execute(
            select(ScreenResult).where(
                ScreenResult.run_id == run.run_id, ScreenResult.company_id == cid
            ).limit(1)
        ).scalar()
        if sr is None:
            _set_run(db, run.run_id, progress_count=idx)
            continue
        try:
            alive, layer_res = eval_fn(db, cid, run.as_of_date, config, run.user_id, run.run_id)
            results = dict(sr.layer_results or {})
            results[layer] = layer_res
            sr.layer_results = results
            merged = list(sr.reason_codes or []) + list(layer_res.get("reason_codes") or [])
            sr.reason_codes = merged
            snap = dict(sr.metrics_snapshot or {})
            snap.update(layer_res.get("metrics") or {})
            sr.metrics_snapshot = snap
            if layer_res.get("ai_result_id"):
                sr.ai_result_id = layer_res["ai_result_id"]
            if not alive:
                sr.rejected_at_layer = layer
                sr.status = "Rejected"
            db.add(sr)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.exception("%s layer failed for %s: %s", layer, cid, e)
        comp = db.get(Company, cid)
        _set_run(db, run.run_id, progress_count=idx,
                 current_company_name=comp.name if comp else None)

    _recount(db, run.run_id)


def _run_one_layer(db: Session, run_id: int, layer: str) -> None:
    run = db.get(ScreenRun, run_id)
    config = _config_from_run(run)
    if layer == "roce":
        _run_roce_layer(db, run, config)
    else:
        _run_ai_layer(db, run, config, layer)


def _finalize(db: Session, run_id: int) -> None:
    """三层跑完：存活者状态置 HighConviction，run 终态。"""
    db.execute(
        update(ScreenResult)
        .where(ScreenResult.run_id == run_id, ScreenResult.rejected_at_layer.is_(None))
        .values(status="HighConviction")
    )
    db.commit()
    _recount(db, run_id)
    _set_run(db, run_id, current_layer="done", layer_status="completed",
             status="completed", finished_at=datetime.now(), current_company_name=None)


def run_from(run_id: int, start_layer: str) -> None:
    """从 start_layer 开始执行。auto_advance=True 则连跑到 done；否则跑一层停在 awaiting_review。

    后台任务入口（自带 DB 会话）。
    """
    db = SessionLocal()
    try:
        layer = start_layer
        while layer in LAYERS:
            _run_one_layer(db, run_id, layer)
            run = db.get(ScreenRun, run_id)
            nxt = _NEXT[layer]
            if run.auto_advance:
                if nxt == "done":
                    _finalize(db, run_id)
                    return
                layer = nxt
                continue
            # 非 auto（auto_advance=False）：每层跑完停在 awaiting_review。
            # 注：HTTP 人工 gate 端点（/advance、/manual）已移除，此分支当前无外部推进入口，
            # 仅保留引擎能力；默认全自动见上方 auto_advance 分支。
            _set_run(db, run_id, current_layer=layer, layer_status="awaiting_review",
                     current_company_name=None)
            return
    except Exception as e:  # noqa: BLE001
        log.exception("run_from failed run=%s layer=%s: %s", run_id, start_layer, e)
        _set_run(db, run_id, layer_status="failed", status="failed",
                 error_msg=str(e)[:500])
    finally:
        db.close()


def start_run(run_id: int) -> None:
    """初次启动：从 ROCE 层开始。"""
    run_from(run_id, "roce")


def finalize_run(run_id: int) -> None:
    """风险层复核完成后定稿（存活者置 HighConviction + completed）。后台任务入口。"""
    db = SessionLocal()
    try:
        _finalize(db, run_id)
    except Exception as e:  # noqa: BLE001
        log.exception("finalize_run failed run=%s: %s", run_id, e)
        _set_run(db, run_id, layer_status="failed", status="failed",
                 error_msg=str(e)[:500])
    finally:
        db.close()
