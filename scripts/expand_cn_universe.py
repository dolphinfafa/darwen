# -*- coding: utf-8 -*-
"""扩展 A股股票池：沪深300 + 中证500 + 中证1000 成分股全量入库。

从 Tushare `index_weight` 取三大指数最新成分（去重 ~1800 只），对**尚未完整入库**的股票
调 `ingest_one_stock`（公司信息 + 三表 + 披露日期 + 行情 + 公告）。

特性：
- **可恢复**：跳过已有财务 fact 的公司（中断后重跑只补未完成的），不重复拉取。
- **限速 + 重试**：每股间隔 + 对 Tushare 限频异常指数退避重试（避免触发配额封禁）。
- **进度日志**：每 N 只打印累计成功/失败/跳过。

用法：
    python -m scripts.expand_cn_universe                 # 全量（三指数）
    python -m scripts.expand_cn_universe --limit 5       # 调试只处理前 5 只新股
    python -m scripts.expand_cn_universe --indices 000300.SH   # 仅沪深300
"""
from __future__ import annotations

import argparse
import time

from loguru import logger
from sqlalchemy import select, func

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.fact import Fact
from backend.pipeline.cn_stock_v2.tushare_client import (
    get_pro, ingest_one_stock, _make_company_id,
)

INDICES = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}
THROTTLE_SEC = 0.35          # 每股之间基础间隔（控总调用频率，约 ≤170 股/分）
MAX_RETRY = 4                # 单股限频重试次数


def fetch_index_members(pro, index_code: str) -> dict[str, None]:
    """取指数最新一期成分股代码（去 .SH/.SZ 后缀的 6 位 code）。"""
    # index_weight 按月发布，取近 90 天窗口的最新一期
    for win in (("20260401", "20260630"), ("20251101", "20260201"), ("20250801", "20251101")):
        df = pro.index_weight(index_code=index_code, start_date=win[0], end_date=win[1])
        if df is not None and not df.empty:
            latest = df["trade_date"].max()
            df = df[df["trade_date"] == latest]
            return {str(c)[:6]: None for c in df["con_code"].tolist()}
    return {}


def _already_ingested(db) -> set[str]:
    """已完整入库的 CN 公司（有 ≥1 条 fact）的 stock_code 集合。"""
    rows = db.execute(
        select(Company.stock_code)
        .join(Fact, Fact.company_id == Company.company_id)
        .where(Company.market == "CN_A")
        .group_by(Company.stock_code)
        .having(func.count(Fact.fact_id) > 0)
    ).all()
    return {r[0] for r in rows if r[0]}


def expand(indices: list[str], *, limit: int | None = None,
           start_date: str = "20140101") -> dict:
    pro = get_pro()
    # 1) 汇总三指数成分（去重）
    universe: dict[str, None] = {}
    for idx in indices:
        members = fetch_index_members(pro, idx)
        logger.info(f"{INDICES.get(idx, idx)} 成分 {len(members)} 只")
        universe.update(members)
    all_codes = sorted(universe)
    logger.info(f"三指数去重后共 {len(all_codes)} 只")

    # 2) 跳过已完整入库的
    db = SessionLocal()
    try:
        done = _already_ingested(db)
        todo = [c for c in all_codes if c not in done]
        logger.info(f"已入库 {len(done)} 只，待入库 {len(todo)} 只")
        if limit:
            todo = todo[:limit]
            logger.info(f"--limit {limit}：本次只处理 {len(todo)} 只")

        stat = {"total_universe": len(all_codes), "already": len(done),
                "todo": len(todo), "ok": 0, "failed": 0, "errors": []}
        for i, code in enumerate(todo, 1):
            for attempt in range(MAX_RETRY):
                try:
                    res = ingest_one_stock(db, code, None, start_date=start_date)
                    if res.get("status") == "ok":
                        stat["ok"] += 1
                    else:
                        stat["failed"] += 1
                        stat["errors"].append((code, res.get("error", "?")[:120]))
                    break
                except Exception as e:  # noqa: BLE001 —— 多为 Tushare 限频
                    msg = str(e)
                    if attempt < MAX_RETRY - 1 and ("每分钟" in msg or "limit" in msg.lower()
                                                    or "频" in msg or "timeout" in msg.lower()):
                        wait = 2 ** (attempt + 1) * 5  # 10/20/40s 退避
                        logger.warning(f"{code} 限频/超时，{wait}s 后重试 ({attempt+1}/{MAX_RETRY})")
                        time.sleep(wait)
                        continue
                    db.rollback()
                    stat["failed"] += 1
                    stat["errors"].append((code, msg[:120]))
                    break
            if i % 20 == 0:
                logger.info(f"进度 {i}/{len(todo)}  ok={stat['ok']} failed={stat['failed']}")
            time.sleep(THROTTLE_SEC)
        return stat
    finally:
        db.close()


if __name__ == "__main__":
    import json

    p = argparse.ArgumentParser(description="扩展 A股股票池（沪深300+中证500+中证1000）")
    p.add_argument("--indices", nargs="*", default=list(INDICES),
                   help="指数代码（默认三大指数）")
    p.add_argument("--limit", type=int, default=None, help="只处理前 N 只新股（调试）")
    p.add_argument("--start-date", default="20140101")
    args = p.parse_args()

    res = expand(args.indices, limit=args.limit, start_date=args.start_date)
    summary = {k: v for k, v in res.items() if k != "errors"}
    summary["error_count"] = len(res["errors"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if res["errors"]:
        print("\n前 10 个错误:")
        for code, msg in res["errors"][:10]:
            print(f"  {code}: {msg}")
