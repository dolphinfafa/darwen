# -*- coding: utf-8 -*-
"""A 股 market_bar 不复权数据修补（数据修补任务）。

问题：V1 时代用 akshare 拉的 A 股 close 是后复权（hfq）价格，导致
valuation 模块 close × shares 算出的市值严重失真（茅台 mc 11T vs 实际 1.7T）。

修复：
1. 删除 50 家 A 股的 market_bar 全部历史行
2. 调 Tushare pro.daily（默认不复权）+ pro.daily_basic（total_mv 万元）
   重拉 2014-至今，写入 market_bar.{open,high,low,close,volume,market_cap}

修复后茅台 PE 应回到 ~22x（与公开数据吻合）。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.market_bar import MarketBar
from backend.models.security import Security
from backend.pipeline.cn_stock_v2.tushare_client import ingest_daily


log = logging.getLogger(__name__)


def truncate_cn_market_bar(db: Session, company_ids: list[str]) -> int:
    """删除指定 A 股的 market_bar 数据。"""
    sec_ids = [r[0] for r in db.execute(
        select(Security.security_id).where(Security.company_id.in_(company_ids))
    ).all()]
    if not sec_ids:
        return 0
    result = db.execute(
        delete(MarketBar).where(MarketBar.security_id.in_(sec_ids))
    )
    db.commit()
    return result.rowcount


def fix_all_cn(*, start_date: str = "20140101", log_every: int = 5) -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Company.company_id, Company.stock_code, Company.name)
            .where(and_(Company.market == "CN_A", Company.stock_code.isnot(None)))
            .order_by(Company.stock_code)
        ).all()
        company_ids = [r[0] for r in rows]

        # 1. truncate
        deleted = truncate_cn_market_bar(db, company_ids)
        log.info("已删除 %d 行旧 market_bar", deleted)

        # 2. 重拉
        total = len(rows)
        ok = 0
        agg_bars = 0
        errors: list[tuple[str, str]] = []
        for i, (cid, code, name) in enumerate(rows, 1):
            try:
                inserted = ingest_daily(db, code, start_date=start_date)
                agg_bars += inserted
                ok += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append((cid, str(e)[:200]))
                log.exception("ingest_daily failed for %s", cid)
            if i % log_every == 0:
                log.info("进度 %d/%d ok=%d bars=%d errors=%d", i, total, ok, agg_bars, len(errors))
            # Tushare 速率：daily 接口 200 req/min（付费），保险加 0.05s 间隔
            time.sleep(0.05)

        return {
            "total": total, "ok": ok,
            "deleted_bars": deleted,
            "inserted_bars": agg_bars,
            "errors": errors,
        }
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="A 股 market_bar 不复权修补")
    parser.add_argument("--start", default="20140101", help="起始日期 yyyymmdd")
    args = parser.parse_args()

    res = fix_all_cn(start_date=args.start)
    summary = {k: v for k, v in res.items() if k != "errors"}
    summary["error_count"] = len(res["errors"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if res["errors"]:
        print("\n前 5 个错误:")
        for cid, msg in res["errors"][:5]:
            print(f"  {cid}: {msg}")
