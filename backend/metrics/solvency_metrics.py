# -*- coding: utf-8 -*-
"""偿付与营运资本风险指标（formula_version=solvency_v1）。

阶段 1b：补营运资本明细字段（retained_earnings / AR / inventory / AP / cogs）后解锁——
- altman_z  Altman Z'' 账面修正版（跨行业、不依赖市值）
            = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
            X1=(流动资产−流动负债)/总资产  X2=留存收益/总资产
            X3=EBIT/总资产                X4=股东权益/总负债
            缺留存收益（A股 TS-FS 暂无）→ altman_z 置 None（降级跳过）
- ccc       现金周转周期(天) = DSO + DIO − DPO
            DSO=AR/营收·365  DIO=存货/COGS·365  DPO=应付/COGS·365
            COGS 缺（美股）→ 用 营收 − 毛利 反推
- ar_growth_lead / inv_growth_lead  应收/存货同比增速 − 营收同比增速
            （持续为正 ⇒ 应收/存货增长持续快于收入，收入质量/虚增隐患）

截面 gate：altman_z_latest / ccc_latest / ccc_delta_3y / ar_lead_3y / inv_lead_3y。
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

FORMULA_VERSION = "solvency_v1"

_FIELDS = (
    "current_assets", "current_liabilities", "total_assets", "total_liabilities",
    "stockholders_equity", "retained_earnings", "operating_income", "revenue",
    "accounts_receivable", "inventory", "accounts_payable", "cogs", "gross_profit",
)


@dataclass
class SolvencyComponents:
    year: int
    period_end: Optional[date]
    market: str
    altman_z: Optional[float] = None
    ccc: Optional[float] = None
    dso: Optional[float] = None
    dio: Optional[float] = None
    dpo: Optional[float] = None
    ar_growth_lead: Optional[float] = None
    inv_growth_lead: Optional[float] = None
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class SolvencyGate:
    altman_z_latest: Optional[float]     # <1.1 hard(破产风险) / 1.1~2.6 soft(灰区)
    ccc_latest: Optional[float]          # 现金周转周期天数（展示/趋势用）
    ccc_delta_3y: Optional[float]        # 近 3 年 CCC 变化（恶化 = 占用现金上升）
    ar_lead_3y: Optional[float]          # 近 3Y 应收增速领先营收均值（>阈值 = 隐患）
    inv_lead_3y: Optional[float]         # 近 3Y 存货增速领先营收均值


def _bulk(db, company_id, year_range, market, fy_end_month):
    out: dict[str, dict[int, FactValue]] = {}
    for c in _FIELDS:
        series = get_annual_periods(
            db, company_id, c, year_range, market=market, fiscal_year_end_month=fy_end_month,
        )
        out[c] = {fv.period_end.year: fv for fv in series if fv.period_end}
    return out


def _v(d: dict[int, FactValue], year: int) -> Optional[float]:
    fv = d.get(year)
    return fv.value if fv and fv.value is not None else None


def compute_solvency_series(
    db: Session, company_id: str, year_range: tuple[int, int],
    *, market: Optional[str] = None, fiscal_year_end_month: Optional[int] = None,
) -> list[SolvencyComponents]:
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    cache = _bulk(db, company_id, year_range, market, fiscal_year_end_month)
    out: list[SolvencyComponents] = []
    for year in range(year_range[0], year_range[1] + 1):
        ca = _v(cache["current_assets"], year)
        cl = _v(cache["current_liabilities"], year)
        ta = _v(cache["total_assets"], year)
        tl = _v(cache["total_liabilities"], year)
        eq = _v(cache["stockholders_equity"], year)
        re = _v(cache["retained_earnings"], year)
        ebit = _v(cache["operating_income"], year)
        rev = _v(cache["revenue"], year)
        ar = _v(cache["accounts_receivable"], year)
        inv = _v(cache["inventory"], year)
        ap = _v(cache["accounts_payable"], year)
        cogs = _v(cache["cogs"], year)
        gp = _v(cache["gross_profit"], year)
        if cogs is None and rev is not None and gp is not None:
            cogs = rev - gp

        pe_fv = cache["total_assets"].get(year) or cache["revenue"].get(year)
        comp = SolvencyComponents(
            year=year, period_end=pe_fv.period_end if pe_fv else None, market=market,
        )

        # Altman Z''（账面修正版）
        if ta and ta > 0:
            x1 = (ca - cl) / ta if (ca is not None and cl is not None) else None
            x2 = re / ta if re is not None else None
            x3 = ebit / ta if ebit is not None else None
            x4 = eq / tl if (eq is not None and tl and tl > 0) else None
            if None not in (x1, x2, x3, x4):
                comp.altman_z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

        # 现金周转周期 CCC
        if rev and rev > 0 and ar is not None:
            comp.dso = ar / rev * 365.0
        if cogs and cogs > 0:
            if inv is not None:
                comp.dio = inv / cogs * 365.0
            if ap is not None:
                comp.dpo = ap / cogs * 365.0
        if comp.dso is not None and comp.dio is not None and comp.dpo is not None:
            comp.ccc = comp.dso + comp.dio - comp.dpo

        # 应收 / 存货增速领先营收（需上一年）
        ar_p = _v(cache["accounts_receivable"], year - 1)
        inv_p = _v(cache["inventory"], year - 1)
        rev_p = _v(cache["revenue"], year - 1)
        if rev and rev_p and rev_p != 0:
            rev_g = rev / rev_p - 1
            if ar is not None and ar_p not in (None, 0):
                comp.ar_growth_lead = (ar / ar_p - 1) - rev_g
            if inv is not None and inv_p not in (None, 0):
                comp.inv_growth_lead = (inv / inv_p - 1) - rev_g

        out.append(comp)
    return out


def evaluate_solvency_gate(series: list[SolvencyComponents]) -> SolvencyGate:
    valid = [c for c in series if c.period_end is not None]

    def _latest(attr):
        for c in reversed(valid):
            v = getattr(c, attr)
            if v is not None:
                return v
        return None

    ccc_vals = [c.ccc for c in valid if c.ccc is not None]
    ccc_delta = ccc_vals[-1] - ccc_vals[-4] if len(ccc_vals) >= 4 else None
    arl = [c.ar_growth_lead for c in valid[-3:] if c.ar_growth_lead is not None]
    ivl = [c.inv_growth_lead for c in valid[-3:] if c.inv_growth_lead is not None]

    return SolvencyGate(
        altman_z_latest=_latest("altman_z"),
        ccc_latest=_latest("ccc"),
        ccc_delta_3y=ccc_delta,
        ar_lead_3y=statistics.mean(arl) if arl else None,
        inv_lead_3y=statistics.mean(ivl) if ivl else None,
    )
