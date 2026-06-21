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


def _safe_float(val):
    try:
        v = float(val)
        return v if pd.notna(v) else None
    except (ValueError, TypeError):
        return None


def _upsert_us_bars(db: Session, security_id: str, df) -> int:
    """把 yfinance df 增量写入 market_bar（按 trade_date 去重，已有跳过）。"""
    if df is None or df.empty:
        return 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    existing = set(
        r[0] for r in db.execute(
            select(MarketBar.trade_date).where(MarketBar.security_id == security_id)
        ).fetchall()
    )
    batch = []
    for idx, row in df.iterrows():
        td = idx.date() if hasattr(idx, "date") else idx
        if td in existing:
            continue
        close = _safe_float(row.get("Close"))
        if close is None:
            continue
        batch.append(MarketBar(
            security_id=security_id, trade_date=td,
            open=_safe_float(row.get("Open")), high=_safe_float(row.get("High")),
            low=_safe_float(row.get("Low")), close=close,
            volume=_safe_float(row.get("Volume")), market_cap=None,
        ))
    if batch:
        db.add_all(batch)
        db.commit()
    return len(batch)


def ingest_us_latest(db: Session, ticker: str, security_id: str) -> int:
    """按需拉美股最近 5 天日线（取最新收盘价），增量 upsert。"""
    try:
        df = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{ticker} yfinance latest 失败: {e}")
        return 0
    return _upsert_us_bars(db, security_id, df)


def ingest_us_latest_bulk(db: Session, items: list[tuple[str, str]]) -> int:
    """批量拉多只美股最近 5 天（一次 yf.download），增量 upsert。items=[(ticker, security_id)]。"""
    items = [(t, s) for t, s in items if t]
    if not items:
        return 0
    tickers = [t for t, _ in items]
    try:
        df = yf.download(tickers, period="5d", auto_adjust=True, progress=False, group_by="ticker")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"批量 yfinance latest 失败({len(tickers)} 只): {e}")
        return 0
    if df is None or df.empty:
        return 0
    total = 0
    multi = isinstance(df.columns, pd.MultiIndex)
    lvl0 = set(df.columns.get_level_values(0)) if multi else set()
    for ticker, sid in items:
        try:
            sub = df[ticker].copy() if (multi and ticker in lvl0) else df
            total += _upsert_us_bars(db, sid, sub)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{ticker} 批量解析失败: {e}")
    return total


def ingest_cn_prices(db: Session, ticker: str, security_id: str, start: str = "20080101") -> int:
    """通过 akshare 拉取单只A股历史日线（前复权）"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, adjust="hfq")
        if df is None or df.empty:
            return 0
    except Exception as e:
        logger.warning(f"{ticker} akshare 失败: {e}")
        return 0

    existing_dates = set(
        row[0] for row in db.execute(
            select(MarketBar.trade_date).where(MarketBar.security_id == security_id)
        ).fetchall()
    )

    batch = []
    for _, row in df.iterrows():
        trade_date = pd.to_datetime(row["日期"]).date()
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
            open=safe_float(row.get("开盘")),
            high=safe_float(row.get("最高")),
            low=safe_float(row.get("最低")),
            close=safe_float(row.get("收盘")),
            volume=safe_float(row.get("成交量")),
            market_cap=None,
        ))

    if batch:
        db.add_all(batch)
        db.commit()

    return len(batch)


def ingest_all_cn_prices(db: Session):
    """批量拉取所有A股证券的历史价格"""
    from backend.models import Company
    # 找所有A股公司对应的 security
    cn_secs = db.execute(
        select(Security).join(Company, Company.company_id == Security.company_id)
        .where(Company.market == "CN_A")
    ).scalars().all()

    logger.info(f"待拉取 {len(cn_secs)} 只A股行情")

    success = 0
    for i, sec in enumerate(cn_secs):
        n = ingest_cn_prices(db, sec.ticker, sec.security_id)
        if n > 0:
            success += 1
            logger.info(f"  {sec.ticker}: +{n} bars")
        if (i + 1) % 10 == 0:
            logger.info(f"A股行情进度: {i+1}/{len(cn_secs)}, 成功: {success}")

    logger.info(f"A股行情拉取完成: {success}/{len(cn_secs)} 成功")
    return success


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
