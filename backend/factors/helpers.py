# -*- coding: utf-8 -*-
"""因子计算辅助函数：从 fact 表取值、TTM 计算等"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from backend.models import Fact


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
