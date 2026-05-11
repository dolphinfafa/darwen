# -*- coding: utf-8 -*-
"""稀释指标（PRD R3 风险层依赖）。

输出：
- shares_outstanding（年度，每年一行）
- share_count_cagr_5y（截面，最近 5 年股本复合增长率）

PRD R3 风险触发（R 层判定，本模块只算原始值）：
- 5Y share_count_cagr > 3% 且 ROCE 未改善 → 高频稀释

降级标签：
- INSUFFICIENT_YEARS_FOR_CAGR  少于 6 年数据
- POSSIBLE_STOCK_SPLIT          单年跳跃 ≥ 1.5x 或 ≤ 0.67x，CAGR 信号可能假阳
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from backend.metrics.helpers import (
    FactValue,
    _get_market,
    get_annual_periods,
    get_fiscal_year_end,
)


FORMULA_VERSION = "dilution_v1"


@dataclass
class DilutionYear:
    year: int
    period_end: Optional[date]
    shares_outstanding: Optional[float]
    source_fact_id: Optional[str]
    source_type: Optional[str]


@dataclass
class DilutionGate:
    n_years: int
    shares_first: Optional[float]   # 5 年前股本
    shares_last: Optional[float]    # 最新股本
    share_count_cagr_5y: Optional[float]
    notes: list[str] = field(default_factory=list)


def compute_dilution_series(
    db: Session,
    company_id: str,
    year_range: tuple[int, int],
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
) -> list[DilutionYear]:
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    series = get_annual_periods(
        db, company_id, "shares_outstanding", year_range,
        market=market, fiscal_year_end_month=fiscal_year_end_month,
    )
    by_year: dict[int, FactValue] = {fv.period_end.year: fv for fv in series if fv.period_end}
    out: list[DilutionYear] = []
    for year in range(year_range[0], year_range[1] + 1):
        fv = by_year.get(year)
        if fv:
            out.append(
                DilutionYear(
                    year=year,
                    period_end=fv.period_end,
                    shares_outstanding=fv.value,
                    source_fact_id=fv.fact_id,
                    source_type=fv.source_type,
                )
            )
        else:
            out.append(DilutionYear(year=year, period_end=None, shares_outstanding=None,
                                     source_fact_id=None, source_type=None))
    return out


def evaluate_dilution_gate(series: list[DilutionYear], *, lookback: int = 5) -> DilutionGate:
    """计算最近 lookback 年的 share_count_cagr。

    取 valid 数据序列的末尾点与前推 lookback 年点。
    若中间单年跳跃 ≥ 1.5x 或 ≤ 0.67x 视为可能拆股，仍计算 CAGR 但打标。
    """
    valid = [y for y in series if y.shares_outstanding is not None and y.shares_outstanding > 0]
    notes: list[str] = []

    if len(valid) < lookback + 1:
        return DilutionGate(
            n_years=len(valid),
            shares_first=None,
            shares_last=None,
            share_count_cagr_5y=None,
            notes=["INSUFFICIENT_YEARS_FOR_CAGR"],
        )

    last = valid[-1]
    first = valid[-(lookback + 1)]

    # 拆股 / 重大股本结构变化检测
    for i in range(1, len(valid)):
        prev = valid[i - 1].shares_outstanding
        cur = valid[i].shares_outstanding
        if prev > 0:
            ratio = cur / prev
            if ratio >= 1.5 or ratio <= 0.67:
                notes.append(f"POSSIBLE_STOCK_SPLIT_{valid[i].year}")

    cagr = (last.shares_outstanding / first.shares_outstanding) ** (1.0 / lookback) - 1.0

    return DilutionGate(
        n_years=len(valid),
        shares_first=first.shares_outstanding,
        shares_last=last.shares_outstanding,
        share_count_cagr_5y=cagr,
        notes=notes,
    )
