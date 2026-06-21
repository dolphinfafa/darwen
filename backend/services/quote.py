# -*- coding: utf-8 -*-
"""按需行情刷新：进股票详情页 / 我的股票池页面时拉最新收盘价。

策略：当天去重（同一 security 当天只拉一次）+ 容错（外部失败不阻塞，降级用库存值）。
美股一次 yf.download 批量拉，A 股逐个 Tushare ingest_daily。
"""
from __future__ import annotations

from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.security import Security
from backend.models.market_bar import MarketBar
from backend.metrics.valuation import _pick_common_security

# 进程级当天去重缓存：security_id -> 最近一次刷新日期
_refreshed: dict[str, date] = {}


def _is_fresh(db: Session, sid: str, today: date) -> bool:
    """当天已刷新过，或 market_bar 最新一根就是今天 → 视为够新，跳过外部拉取。"""
    if _refreshed.get(sid) == today:
        return True
    latest = db.execute(
        select(MarketBar.trade_date)
        .where(MarketBar.security_id == sid)
        .order_by(MarketBar.trade_date.desc())
        .limit(1)
    ).scalar()
    return latest is not None and latest >= today


def refresh_quotes(db: Session, company_ids: list[str]) -> int:
    """拉取这些公司的最新收盘价到 market_bar。美股批量、A 股逐个；当天去重 + 全程容错。

    返回新增 bar 数。任何外部失败都不抛出（页面降级用库存值）。
    """
    today = date.today()
    us_items: list[tuple[str, str]] = []   # (ticker, security_id)
    cn_items: list[tuple[str, str]] = []   # (stock_code, security_id)

    for cid in dict.fromkeys(company_ids):  # 去重保序
        try:
            comp = db.get(Company, cid)
            if comp is None:
                continue
            sid = _pick_common_security(db, cid)
            if not sid or _is_fresh(db, sid, today):
                continue
            if comp.market == "CN_A":
                if comp.stock_code:
                    cn_items.append((comp.stock_code, sid))
            else:
                tk = db.scalar(select(Security.ticker).where(Security.security_id == sid))
                if tk:
                    us_items.append((tk, sid))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"refresh_quotes 预处理 {cid} 失败: {e}")

    total = 0
    if us_items:
        try:
            from backend.pipeline.market_data import ingest_us_latest_bulk
            total += ingest_us_latest_bulk(db, us_items)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"美股批量刷新失败: {e}")
        for _, sid in us_items:
            _refreshed[sid] = today

    if cn_items:
        from backend.pipeline.cn_stock_v2.tushare_client import ingest_daily
        start = (today - timedelta(days=7)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        for code, sid in cn_items:
            try:
                total += ingest_daily(db, code, start_date=start, end_date=end)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"A 股 {code} 刷新失败: {e}")
            _refreshed[sid] = today

    return total


def refresh_quote(db: Session, company_id: str) -> int:
    """单只刷新（详情页用）。"""
    return refresh_quotes(db, [company_id])
