# -*- coding: utf-8 -*-
"""优势积累维度因子 M1-M6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_MOAT
from backend.factors.helpers import get_fact_value, get_annual_values, safe_div
from backend.factors.replication import _calc_invested_capital, _calc_nopat


@register_factor("M1", DIM_MOAT, "定价权/替代性")
def compute_m1(db: Session, company_id: str, asof: date) -> dict:
    """M1: MVP 用毛利率水平作为定价权代理"""
    revenue = get_fact_value(db, company_id, "Revenues", asof) or \
              get_fact_value(db, company_id, "revenue", asof)
    gp = get_fact_value(db, company_id, "GrossProfit", asof)
    if gp is None:
        total_cost = get_fact_value(db, company_id, "total_cost", asof)
        if revenue and total_cost:
            gp = revenue - total_cost

    gross_margin = safe_div(gp, revenue)

    return {"raw": {"pricing_power_proxy": gross_margin}, "redline": None}


@register_factor("M2", DIM_MOAT, "复利可持续性")
def compute_m2(db: Session, company_id: str, asof: date) -> dict:
    """M2: ROIC × 再投资率"""
    nopat = _calc_nopat(db, company_id, asof)
    ic = _calc_invested_capital(db, company_id, asof)
    roic = safe_div(nopat, ic)

    capex = get_fact_value(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", asof) or \
            get_fact_value(db, company_id, "capex_cash", asof) or 0
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    reinvest_rate = safe_div(abs(capex), ocf) if ocf else None

    compounding = (roic * reinvest_rate) if roic and reinvest_rate else None

    return {"raw": {"roic": roic, "reinvest_rate": reinvest_rate, "compounding_score": compounding}, "redline": None}


@register_factor("M3", DIM_MOAT, "市占率/结构性优势")
def compute_m3(db: Session, company_id: str, asof: date) -> dict:
    """M3: MVP 返回中性分（市占率需外部数据）"""
    return {"raw": {"market_share": None}, "redline": None, "stub": True}


@register_factor("M4", DIM_MOAT, "规模与学习曲线")
def compute_m4(db: Session, company_id: str, asof: date) -> dict:
    """M4: SGA 杠杆 — 收入增长快于 SGA 增长"""
    rev_series = get_annual_values(db, company_id, "Revenues", 5, asof) or \
                 get_annual_values(db, company_id, "revenue", 5, asof)
    sga_series = get_annual_values(db, company_id, "SellingGeneralAndAdministrativeExpense", 5, asof)

    # A 股: SGA = 销售费用 + 管理费用
    if not sga_series:
        sell_series = get_annual_values(db, company_id, "selling_expense", 5, asof)
        admin_series = get_annual_values(db, company_id, "admin_expense", 5, asof)
        if sell_series and admin_series and len(sell_series) == len(admin_series):
            sga_series = [s + a for s, a in zip(sell_series, admin_series)]

    sga_leverage = None
    if rev_series and sga_series and len(rev_series) >= 2 and len(sga_series) >= 2:
        rev_growth = (rev_series[0] / rev_series[-1]) if rev_series[-1] and rev_series[-1] > 0 else None
        sga_growth = (sga_series[0] / sga_series[-1]) if sga_series[-1] and sga_series[-1] > 0 else None
        if rev_growth and sga_growth and sga_growth > 0:
            sga_leverage = rev_growth / sga_growth  # >1 意味着规模效应

    return {"raw": {"sga_leverage": sga_leverage}, "redline": None}


@register_factor("M5", DIM_MOAT, "资本配置与反脆弱")
def compute_m5(db: Session, company_id: str, asof: date) -> dict:
    """M5: MVP 返回中性分"""
    return {"raw": {"countercyc_invest_score": None}, "redline": None, "stub": True}


@register_factor("M6", DIM_MOAT, "诚信/叙事一致性（AI）")
def compute_m6(db: Session, company_id: str, asof: date) -> dict:
    """M6: MVP 返回中性分，Phase 2 用 LLM 实现"""
    return {"raw": {"narrative_consistency": None}, "redline": None, "stub": True}
