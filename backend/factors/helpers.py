# -*- coding: utf-8 -*-
"""因子计算辅助函数：从 fact 表取值、TTM 计算等"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func

from backend.models import Fact, Security, MarketBar, Filing


def get_fact_value(
    db: Session,
    company_id: str,
    concept: str,
    asof_date: date,
    lookback_days: int = 400,
) -> Optional[float]:
    """获取某公司某概念在 asof_date 前最新的值"""
    earliest = asof_date - timedelta(days=lookback_days)
    stmt = (
        select(Fact.value, Fact.period_end)
        .where(and_(
            Fact.company_id == company_id,
            Fact.concept == concept,
            Fact.period_end <= asof_date,
            Fact.period_end >= earliest,
        ))
        .order_by(Fact.period_end.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    return row[0] if row else None


def get_fact_series(
    db: Session,
    company_id: str,
    concept: str,
    years: int = 5,
    asof_date: date | None = None,
) -> list[tuple[date, float]]:
    """获取某概念的历年值（按 period_end 降序）"""
    if asof_date is None:
        asof_date = date.today()
    earliest = asof_date - timedelta(days=years * 370)
    stmt = (
        select(Fact.period_end, Fact.value)
        .where(and_(
            Fact.company_id == company_id,
            Fact.concept == concept,
            Fact.period_end <= asof_date,
            Fact.period_end >= earliest,
            Fact.value.isnot(None),
        ))
        .order_by(Fact.period_end.desc())
    )
    return [(row[0], row[1]) for row in db.execute(stmt).fetchall()]


def get_annual_values(
    db: Session,
    company_id: str,
    concept: str,
    years: int = 5,
    asof_date: date | None = None,
) -> list[float]:
    """获取年度值列表（从新到旧），仅取年报（period_end 月份为 12 或 9 等）"""
    series = get_fact_series(db, company_id, concept, years, asof_date)
    # 去重同年数据，取每年最晚的
    seen_years = set()
    result = []
    for d, v in series:
        if d.year not in seen_years:
            seen_years.add(d.year)
            result.append(v)
    return result[:years]


def safe_div(a: float | None, b: float | None) -> float | None:
    """安全除法"""
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr(values: list[float], years: int | None = None) -> float | None:
    """计算复合年增长率，values 从新到旧"""
    if len(values) < 2:
        return None
    newest, oldest = values[0], values[-1]
    if oldest <= 0 or newest <= 0:
        return None
    n = years if years else len(values) - 1
    if n <= 0:
        return None
    return (newest / oldest) ** (1.0 / n) - 1.0


def volatility(values: list[float]) -> float | None:
    """计算标准差（归一化）"""
    if len(values) < 2:
        return None
    import numpy as np
    arr = np.array(values, dtype=float)
    mean = np.mean(arr)
    if mean == 0:
        return None
    return float(np.std(arr) / abs(mean))


# ──────────────────── 通用收入取值函数 ────────────────────

_REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "revenue",
]


def get_revenue(db: Session, company_id: str, asof_date: date) -> Optional[float]:
    """获取收入（兼容多种 concept 名称）"""
    for concept in _REVENUE_CONCEPTS:
        val = get_fact_value(db, company_id, concept, asof_date)
        if val is not None:
            return val
    return None


def get_revenue_series(db: Session, company_id: str, years: int = 6, asof_date: date = None) -> list[float]:
    """获取年度收入序列（兼容多种 concept 名称）"""
    for concept in _REVENUE_CONCEPTS:
        series = get_annual_values(db, company_id, concept, years, asof_date)
        if series:
            return series
    return []


# ──────────────────── 行情数据辅助函数 ────────────────────

def _get_security_id(db: Session, company_id: str) -> Optional[str]:
    """获取公司的第一个 security_id"""
    row = db.execute(
        select(Security.security_id).where(Security.company_id == company_id).limit(1)
    ).first()
    return row[0] if row else None


def get_close_prices(
    db: Session,
    company_id: str,
    asof_date: date,
    days: int = 252,
) -> list[tuple[date, float]]:
    """获取 asof_date 前 N 个交易日的收盘价（从旧到新）"""
    sec_id = _get_security_id(db, company_id)
    if not sec_id:
        return []

    stmt = (
        select(MarketBar.trade_date, MarketBar.close)
        .where(and_(
            MarketBar.security_id == sec_id,
            MarketBar.trade_date <= asof_date,
            MarketBar.close.isnot(None),
        ))
        .order_by(MarketBar.trade_date.desc())
        .limit(days)
    )
    rows = db.execute(stmt).fetchall()
    return [(r[0], r[1]) for r in reversed(rows)]  # 旧→新


def get_volume_series(
    db: Session,
    company_id: str,
    asof_date: date,
    days: int = 20,
) -> list[float]:
    """获取 asof_date 前 N 个交易日的成交量"""
    sec_id = _get_security_id(db, company_id)
    if not sec_id:
        return []

    stmt = (
        select(MarketBar.volume)
        .where(and_(
            MarketBar.security_id == sec_id,
            MarketBar.trade_date <= asof_date,
            MarketBar.volume.isnot(None),
            MarketBar.volume > 0,
        ))
        .order_by(MarketBar.trade_date.desc())
        .limit(days)
    )
    return [r[0] for r in db.execute(stmt).fetchall()]


def get_filing_count(
    db: Session,
    company_id: str,
    asof_date: date,
    form_types: list[str] | None = None,
    years: int = 3,
) -> int:
    """获取公司在指定期间内的 filing 数量"""
    earliest = asof_date - timedelta(days=years * 365)
    stmt = (
        select(func.count())
        .select_from(Filing)
        .where(and_(
            Filing.company_id == company_id,
            Filing.filed_date <= asof_date,
            Filing.filed_date >= earliest,
        ))
    )
    if form_types:
        stmt = stmt.where(Filing.form_type.in_(form_types))
    row = db.execute(stmt).first()
    return row[0] if row else 0
