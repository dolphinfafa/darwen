# -*- coding: utf-8 -*-
"""现金质量指标（PRD R2 风险层依赖）。

输出：
- cfo_ni_ratio = CFO / NetIncome（年度）
- fcf = fcf_reported（Tushare 直给）→ fallback CFO - CapEx
- fcf_neg_year（标记 FCF < 0 的年）

R2 风险触发（由 R 层判定，本模块只算原始值 + 5Y 统计）：
- CFO/NetIncome < 0.7 连续 2 年
- FCF<0 在 5 年中 ≥ 3 年

降级标签：
- NET_INCOME_NONPOSITIVE          净利润 ≤ 0，cfo_ni_ratio=None
- FCF_FROM_CFO_MINUS_CAPEX        FCF 用回退公式
- FCF_NOT_AVAILABLE                CFO 与 CapEx 任一缺失
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


FORMULA_VERSION = "cash_quality_v1"


@dataclass
class CashQualityComponents:
    year: int
    period_end: Optional[date]
    market: str

    cfo: Optional[float] = None
    net_income: Optional[float] = None
    cfo_ni_ratio: Optional[float] = None
    capex: Optional[float] = None
    fcf: Optional[float] = None

    notes: list[str] = field(default_factory=list)
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)

    @property
    def fcf_negative(self) -> Optional[bool]:
        return None if self.fcf is None else self.fcf < 0

    @property
    def cfo_ni_below_07(self) -> Optional[bool]:
        return None if self.cfo_ni_ratio is None else self.cfo_ni_ratio < 0.7


@dataclass
class CashQualityGate:
    """5Y 现金质量截面统计，供 R2 触发判定。"""
    n_recent_years: int
    cfo_ni_5y_below_07_years: int
    cfo_ni_5y_consec_below_07: int  # 最近连续 < 0.7 的年数（R2: ≥ 2 触发）
    fcf_neg_5y_years: int           # R2: ≥ 3/5 触发
    median_cfo_ni_5y: Optional[float]


_FIELDS = (
    "cfo",
    "net_income",
    "capex",
    "fcf_reported",
)


def _bulk_fetch(
    db: Session,
    company_id: str,
    canonicals: tuple[str, ...],
    year_range: tuple[int, int],
    market: str,
    fy_end_month: Optional[int],
) -> dict[str, dict[int, FactValue]]:
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
) -> CashQualityComponents:
    comp = CashQualityComponents(year=year, period_end=None, market=market)

    cfo = cache.get("cfo", {}).get(year)
    ni = cache.get("net_income", {}).get(year)
    capex = cache.get("capex", {}).get(year)
    fcf_rep = cache.get("fcf_reported", {}).get(year)

    if cfo and cfo.period_end:
        comp.period_end = cfo.period_end
    elif ni and ni.period_end:
        comp.period_end = ni.period_end

    # ===== cfo / net_income =====
    if cfo is None or cfo.value is None:
        comp.notes.append("CFO_MISSING")
    else:
        comp.cfo = cfo.value
        comp.source_fact_ids["cfo"] = cfo.fact_id

    if ni is None or ni.value is None:
        comp.notes.append("NET_INCOME_MISSING")
    elif ni.value <= 0:
        comp.net_income = ni.value
        comp.source_fact_ids["net_income"] = ni.fact_id
        comp.notes.append("NET_INCOME_NONPOSITIVE")
    else:
        comp.net_income = ni.value
        comp.source_fact_ids["net_income"] = ni.fact_id

    if comp.cfo is not None and comp.net_income is not None and comp.net_income > 0:
        comp.cfo_ni_ratio = comp.cfo / comp.net_income

    # ===== FCF =====
    # 优先 CFO - CapEx（PRD R2 标准公式，口径稳定）
    # fcf_reported 仅在 capex 缺失时兜底（Tushare fcf 字段口径未文档化，偶有脏值）
    if comp.cfo is not None and capex is not None and capex.value is not None:
        comp.capex = capex.value
        comp.source_fact_ids["capex"] = capex.fact_id
        comp.fcf = comp.cfo - capex.value
    elif fcf_rep is not None and fcf_rep.value is not None:
        comp.fcf = fcf_rep.value
        comp.source_fact_ids["fcf"] = fcf_rep.fact_id
        comp.notes.append("FCF_FROM_REPORTED_FALLBACK")
    else:
        comp.notes.append("FCF_NOT_AVAILABLE")

    return comp


def compute_cash_quality_series(
    db: Session,
    company_id: str,
    year_range: tuple[int, int],
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
) -> list[CashQualityComponents]:
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    cache = _bulk_fetch(db, company_id, _FIELDS, year_range, market, fiscal_year_end_month)
    return [_compute_one_year(year, market, cache) for year in range(year_range[0], year_range[1] + 1)]


def evaluate_cash_quality_gate(
    series: list[CashQualityComponents],
    *,
    recent_n: int = 5,
) -> CashQualityGate:
    """统计最近 N 年现金质量信号供 R2 触发判定。"""
    recent = [c for c in series if c.period_end is not None][-recent_n:]
    n_recent = len(recent)

    below_07_years = sum(1 for c in recent if c.cfo_ni_below_07 is True)
    fcf_neg_years = sum(1 for c in recent if c.fcf_negative is True)

    # 最近连续 < 0.7 的年数（从末尾向前数）
    consec_below = 0
    for c in reversed(recent):
        if c.cfo_ni_below_07 is True:
            consec_below += 1
        else:
            break

    cfo_ni_values = [c.cfo_ni_ratio for c in recent if c.cfo_ni_ratio is not None]
    median_cfo_ni = None
    if cfo_ni_values:
        import statistics
        median_cfo_ni = statistics.median(cfo_ni_values)

    return CashQualityGate(
        n_recent_years=n_recent,
        cfo_ni_5y_below_07_years=below_07_years,
        cfo_ni_5y_consec_below_07=consec_below,
        fcf_neg_5y_years=fcf_neg_years,
        median_cfo_ni_5y=median_cfo_ni,
    )
