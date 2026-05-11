# -*- coding: utf-8 -*-
"""杠杆指标（PRD R1 风险层依赖）。

输出：
- net_debt = short_term_debt + current_portion_long_term_debt + long_term_debt - cash - short_term_investments
- net_debt_ebit = net_debt / EBIT
- interest_coverage = EBIT / |interest_expense|
- current_ratio = current_assets / current_liabilities

PRD R1 风险触发：
- interest_coverage < 3
- net_debt/EBIT > 4
- current_ratio < 1 且连续 2 年恶化（R 层判定，本模块只算原始值）

降级标签：
- INTEREST_EXPENSE_ZERO_OR_MISSING   利息费用 0 或缺失，interest_coverage=None
- EBIT_MISSING_FOR_LEVERAGE_RATIO    无 EBIT 时 net_debt/EBIT=None
- NET_DEBT_NEGATIVE                  净债为负（现金 > 全部带息债务，PRD 允许）
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


FORMULA_VERSION = "leverage_v1"


@dataclass
class LeverageComponents:
    year: int
    period_end: Optional[date]
    market: str

    short_term_debt: Optional[float] = None
    current_portion_long_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    cash: Optional[float] = None
    short_term_investments: Optional[float] = None

    net_debt: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    net_debt_ebit: Optional[float] = None  # 需要外部 ebit 传入

    notes: list[str] = field(default_factory=list)
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)


_FIELDS = (
    "short_term_debt",
    "current_portion_long_term_debt",
    "long_term_debt",
    "cash",
    "short_term_investments",
    "current_assets",
    "current_liabilities",
    "interest_expense",
)


def _bulk_fetch(
    db: Session,
    company_id: str,
    canonicals: tuple[str, ...],
    year_range: tuple[int, int],
    market: str,
    fy_end_month: Optional[int],
) -> dict[str, dict[int, FactValue]]:
    """复用与 roce 同样的批量预拉模式。"""
    out: dict[str, dict[int, FactValue]] = {}
    for canonical in canonicals:
        series = get_annual_periods(
            db, company_id, canonical, year_range,
            market=market, fiscal_year_end_month=fy_end_month,
        )
        out[canonical] = {fv.period_end.year: fv for fv in series if fv.period_end}
    return out


def _compute_one_year(
    year: int,
    market: str,
    cache: dict[str, dict[int, FactValue]],
    ebit_value: Optional[float],
) -> LeverageComponents:
    comp = LeverageComponents(year=year, period_end=None, market=market)

    std = cache.get("short_term_debt", {}).get(year)
    cpltd = cache.get("current_portion_long_term_debt", {}).get(year)
    ltd = cache.get("long_term_debt", {}).get(year)
    cash = cache.get("cash", {}).get(year)
    sti = cache.get("short_term_investments", {}).get(year)
    ca = cache.get("current_assets", {}).get(year)
    cl = cache.get("current_liabilities", {}).get(year)
    ie = cache.get("interest_expense", {}).get(year)

    # 取 period_end 代表（优先用 long_term_debt 的，cash 的也行）
    for fv in (ltd, cash, ca, cl):
        if fv and fv.period_end:
            comp.period_end = fv.period_end
            break

    # ===== net_debt =====
    if cash is None or cash.value is None:
        comp.notes.append("CASH_MISSING")
    else:
        comp.cash = cash.value
        comp.source_fact_ids["cash"] = cash.fact_id

        debt_components = 0.0
        all_debt_missing = True
        for name, fv in (("short_term_debt", std),
                         ("current_portion_long_term_debt", cpltd),
                         ("long_term_debt", ltd)):
            if fv and fv.value is not None:
                debt_components += fv.value
                setattr(comp, name, fv.value)
                comp.source_fact_ids[name] = fv.fact_id
                all_debt_missing = False
            else:
                comp.source_fact_ids[name] = None

        if all_debt_missing:
            comp.notes.append("ALL_DEBT_FIELDS_MISSING")
        else:
            sti_value = sti.value if (sti and sti.value is not None) else 0.0
            if sti is None or sti.value is None:
                comp.source_fact_ids["short_term_investments"] = None
                comp.notes.append("STI_ZEROED")
            else:
                comp.short_term_investments = sti.value
                comp.source_fact_ids["short_term_investments"] = sti.fact_id

            comp.net_debt = debt_components - cash.value - sti_value
            if comp.net_debt < 0:
                comp.notes.append("NET_DEBT_NEGATIVE")

    # ===== net_debt / EBIT =====
    if ebit_value is not None and ebit_value != 0 and comp.net_debt is not None:
        comp.net_debt_ebit = comp.net_debt / ebit_value
    elif ebit_value is None:
        comp.notes.append("EBIT_MISSING_FOR_LEVERAGE_RATIO")

    # ===== interest_coverage = EBIT / |interest_expense| =====
    if ebit_value is None:
        pass  # 已记 EBIT_MISSING
    elif ie is None or ie.value is None or ie.value == 0:
        comp.notes.append("INTEREST_EXPENSE_ZERO_OR_MISSING")
    else:
        # A 股 finance_expense 可能为负（利息净额，理财收益压低费用）
        denom = abs(ie.value)
        if denom > 0:
            comp.interest_coverage = ebit_value / denom
            comp.source_fact_ids["interest_expense"] = ie.fact_id

    # ===== current_ratio =====
    if ca is None or ca.value is None:
        comp.notes.append("CURRENT_ASSETS_MISSING")
    elif cl is None or cl.value is None or cl.value == 0:
        comp.notes.append("CURRENT_LIAB_MISSING_OR_ZERO")
    else:
        comp.current_ratio = ca.value / cl.value
        comp.source_fact_ids["current_assets"] = ca.fact_id
        comp.source_fact_ids["current_liabilities"] = cl.fact_id

    return comp


def compute_leverage_series(
    db: Session,
    company_id: str,
    year_range: tuple[int, int],
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
    ebit_by_year: Optional[dict[int, float]] = None,
) -> list[LeverageComponents]:
    """计算多年杠杆指标序列。

    ebit_by_year：可选，由 ROCE 计算结果传入避免重复求 EBIT。
                  缺则 net_debt_ebit 与 interest_coverage 为 None。
    """
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    cache = _bulk_fetch(db, company_id, _FIELDS, year_range, market, fiscal_year_end_month)
    out: list[LeverageComponents] = []
    for year in range(year_range[0], year_range[1] + 1):
        ebit_v = ebit_by_year.get(year) if ebit_by_year else None
        out.append(_compute_one_year(year, market, cache, ebit_v))
    return out
