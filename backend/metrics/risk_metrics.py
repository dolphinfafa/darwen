# -*- coding: utf-8 -*-
"""财务风险扩展指标（稳健层增强，formula_version=risk_v1）。

阶段 1a（零补字段，复用现有 canonical）：
- accruals_ratio  应计利润率 = (NetIncome − CFO) / 平均总资产；近 3Y 平均 → 利润质量
- fcf_margin       FCF/Revenue（FCF = CFO − CapEx）；近 5Y 变异系数 fcf_cv_5y → 现金流稳定性

阈值与硬/软分档由稳健层（funnel_v2）按 config 判定，本模块只算原始值 + 截面统计。
"""
from __future__ import annotations

import statistics
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

FORMULA_VERSION = "risk_v1"

_FIELDS = ("net_income", "cfo", "capex", "total_assets", "revenue")


@dataclass
class RiskFinComponents:
    year: int
    period_end: Optional[date]
    market: str
    accruals_ratio: Optional[float] = None   # (NI − CFO) / avg_total_assets
    fcf_margin: Optional[float] = None        # (CFO − CapEx) / Revenue
    notes: list[str] = field(default_factory=list)
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class RiskFinGate:
    accruals_3y_avg: Optional[float]   # 近 3Y 应计利润率均值（>10% hard / 5~10% soft）
    fcf_cv_5y: Optional[float]         # 近 5Y FCF margin 变异系数（>1 hard / 0.5~1 soft）


def _bulk(
    db: Session, company_id: str, year_range: tuple[int, int],
    market: str, fy_end_month: Optional[int],
) -> dict[str, dict[int, FactValue]]:
    out: dict[str, dict[int, FactValue]] = {}
    for c in _FIELDS:
        series = get_annual_periods(
            db, company_id, c, year_range, market=market, fiscal_year_end_month=fy_end_month,
        )
        out[c] = {fv.period_end.year: fv for fv in series if fv.period_end}
    return out


def compute_risk_fin_series(
    db: Session, company_id: str, year_range: tuple[int, int],
    *, market: Optional[str] = None, fiscal_year_end_month: Optional[int] = None,
) -> list[RiskFinComponents]:
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    cache = _bulk(db, company_id, year_range, market, fiscal_year_end_month)
    out: list[RiskFinComponents] = []
    for year in range(year_range[0], year_range[1] + 1):
        ni = cache["net_income"].get(year)
        cfo = cache["cfo"].get(year)
        capex = cache["capex"].get(year)
        ta = cache["total_assets"].get(year)
        ta_prev = cache["total_assets"].get(year - 1)
        rev = cache["revenue"].get(year)

        pe = (cfo or ni or ta)
        comp = RiskFinComponents(
            year=year, period_end=pe.period_end if pe else None, market=market,
        )

        # 应计利润率 = (NI − CFO) / 平均总资产
        if (ni and ni.value is not None) and (cfo and cfo.value is not None) and (ta and ta.value):
            avg_ta = ta.value
            if ta_prev and ta_prev.value:
                avg_ta = (ta.value + ta_prev.value) / 2.0
            if avg_ta:
                comp.accruals_ratio = (ni.value - cfo.value) / avg_ta
                comp.source_fact_ids["net_income"] = ni.fact_id
                comp.source_fact_ids["cfo"] = cfo.fact_id
                comp.source_fact_ids["total_assets"] = ta.fact_id

        # FCF margin = (CFO − CapEx) / Revenue
        if (cfo and cfo.value is not None) and (capex and capex.value is not None) and (rev and rev.value):
            comp.fcf_margin = (cfo.value - capex.value) / rev.value
            comp.source_fact_ids.setdefault("cfo", cfo.fact_id)
            comp.source_fact_ids["capex"] = capex.fact_id
            comp.source_fact_ids["revenue"] = rev.fact_id

        out.append(comp)
    return out


def evaluate_risk_fin_gate(series: list[RiskFinComponents]) -> RiskFinGate:
    valid = [c for c in series if c.period_end is not None]
    accr = [c.accruals_ratio for c in valid[-3:] if c.accruals_ratio is not None]
    fcfm = [c.fcf_margin for c in valid[-5:] if c.fcf_margin is not None]

    accruals_3y_avg = statistics.mean(accr) if accr else None
    fcf_cv_5y = None
    if len(fcfm) >= 2:
        m = statistics.mean(fcfm)
        if m != 0:
            fcf_cv_5y = statistics.pstdev(fcfm) / abs(m)
    return RiskFinGate(accruals_3y_avg=accruals_3y_avg, fcf_cv_5y=fcf_cv_5y)
