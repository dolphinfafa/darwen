# -*- coding: utf-8 -*-
"""行情数据拉取：yfinance（美股）"""
from datetime import date

import yfinance as yf
import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.models import Security, MarketBar


def ingest_us_prices(db: Session, ticker: str, security_id: str, start: str = "2008-01-01") -> int:
    """通过 yfinance 拉取单只美股历史日线"""
    try:
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return 0
        # 处理 MultiIndex 列（yfinance 可能返回 (Price, Ticker) 格式）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    except Exception as e:
        logger.warning(f"{ticker} yfinance 失败: {e}")
        return 0

    # 查已有日期
    existing_dates = set(
        row[0] for row in db.execute(
            select(MarketBar.trade_date).where(MarketBar.security_id == security_id)
        ).fetchall()
    )

    batch = []
    for idx, row in df.iterrows():
        trade_date = idx.date() if hasattr(idx, 'date') else idx
        if trade_date in existing_dates:
            continue

        def safe_float(val):
            try:
                v = float(val)
                return v if pd.notna(v) else None
            except (ValueError, TypeError):
                return None

        batch.append(MarketBar(
            security_id=security_id,
            trade_date=trade_date,
            open=safe_float(row.get("Open")),
            high=safe_float(row.get("High")),
            low=safe_float(row.get("Low")),
            close=safe_float(row.get("Close")),
            volume=safe_float(row.get("Volume")),
            market_cap=None,
        ))

    if batch:
        db.add_all(batch)
        db.commit()

    return len(batch)


def ingest_all_us_prices(db: Session):
    """批量拉取所有美股证券的历史价格"""
    securities = db.execute(
        select(Security).where(Security.exchange.isnot(None))
    ).scalars().all()

    # 过滤出有 ticker 的美股
    us_secs = [s for s in securities if s.ticker and not s.ticker.startswith(("6", "0", "3", "8"))]
    logger.info(f"待拉取 {len(us_secs)} 只美股行情")

    success = 0
    for i, sec in enumerate(us_secs):
        n = ingest_us_prices(db, sec.ticker, sec.security_id)
        if n > 0:
            success += 1
        if (i + 1) % 10 == 0:
            logger.info(f"行情进度: {i+1}/{len(us_secs)}, 成功: {success}")

    logger.info(f"行情拉取完成: {success}/{len(us_secs)} 成功")
    return success
