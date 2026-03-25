# -*- coding: utf-8 -*-
"""优势积累维度因子 M1-M6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_MOAT
from backend.factors.helpers import (
    get_fact_value, get_annual_values, safe_div, cagr,
    get_revenue, get_revenue_series,
)
from backend.factors.replication import _calc_invested_capital, _calc_nopat


@register_factor("M1", DIM_MOAT, "定价权/替代性")
def compute_m1(db: Session, company_id: str, asof: date) -> dict:
    """M1: MVP 用毛利率水平作为定价权代理"""
    revenue = get_revenue(db, company_id, asof)
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
    """M3: 市占率代理 — 用收入规模 + 收入增长超行业均值
    无外部市占率数据，用以下代理指标：
    - 收入绝对规模（大公司通常市占率高）
    - 5年收入CAGR（增长快=抢占市场份额）
    综合分 = log(Revenue) × (1 + CAGR)
    """
    revenue = get_revenue(db, company_id, asof)
    rev_series = get_revenue_series(db, company_id, 6, asof)
    rev_cagr = cagr(rev_series) if len(rev_series) >= 2 else None

    import math
    market_share_proxy = None
    if revenue and revenue > 0:
        log_rev = math.log10(revenue)
        if rev_cagr is not None:
            market_share_proxy = log_rev * (1.0 + max(rev_cagr, -0.5))
        else:
            market_share_proxy = log_rev

    return {"raw": {"market_share_proxy": market_share_proxy}, "redline": None}


@register_factor("M4", DIM_MOAT, "规模与学习曲线")
def compute_m4(db: Session, company_id: str, asof: date) -> dict:
    """M4: SGA 杠杆 — 收入增长快于 SGA 增长"""
    rev_series = get_revenue_series(db, company_id, 5, asof)
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
    """M5: 逆周期投资能力 — 在收入下滑年份是否增加 capex 或回购
    逻辑：找到收入下滑的年份，检查该年 capex/revenue 是否上升
    反脆弱分 = 逆周期投入年份占比
    """
    rev_series = get_revenue_series(db, company_id, 6, asof)
    capex_series = get_annual_values(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", 6, asof) or \
                   get_annual_values(db, company_id, "capex_cash", 6, asof)

    if len(rev_series) < 3 or len(capex_series) < 3:
        return {"raw": {"countercyc_invest_score": None}, "redline": None}

    # 取相同长度
    n = min(len(rev_series), len(capex_series))
    rev_series = rev_series[:n]
    capex_series = [abs(c) if c else 0 for c in capex_series[:n]]

    countercyc_years = 0
    downturn_years = 0

    # 从新到旧：index 0 是最新，比较 i 和 i+1
    for i in range(n - 1):
        rev_now, rev_prev = rev_series[i], rev_series[i + 1]
        capex_now, capex_prev = capex_series[i], capex_series[i + 1]

        if rev_prev and rev_prev > 0 and rev_now < rev_prev:
            # 收入下滑年
            downturn_years += 1
            capex_ratio_now = capex_now / rev_now if rev_now > 0 else 0
            capex_ratio_prev = capex_prev / rev_prev if rev_prev > 0 else 0
            if capex_ratio_now >= capex_ratio_prev:
                countercyc_years += 1

    score = safe_div(countercyc_years, downturn_years) if downturn_years > 0 else None
    # 如果没有衰退年份，给一个中性偏高的分
    if downturn_years == 0 and n >= 3:
        score = 0.6  # 没经历衰退，无法判断，给中性偏高

    return {"raw": {"countercyc_invest_score": score}, "redline": None}


@register_factor("M6", DIM_MOAT, "诚信/叙事一致性")
def compute_m6(db: Session, company_id: str, asof: date) -> dict:
    """M6: 叙事一致性代理 — 用管理层 guidance 兑现率近似
    无 LLM 时用财务数据代理：收入增长的波动性越低=执行力越强=叙事一致
    同时考虑利润增长方向与收入增长方向的一致性
    """
    rev_series = get_revenue_series(db, company_id, 6, asof)
    ni_series = get_annual_values(db, company_id, "NetIncomeLoss", 6, asof) or \
                get_annual_values(db, company_id, "net_income", 6, asof)

    if len(rev_series) < 3 or len(ni_series) < 3:
        return {"raw": {"narrative_consistency": None}, "redline": None}

    # 收入增长方向一致性
    n = min(len(rev_series), len(ni_series))
    consistent_years = 0
    total_years = 0

    for i in range(n - 1):
        rev_growth = rev_series[i] - rev_series[i + 1]
        ni_growth = ni_series[i] - ni_series[i + 1]
        # 收入和利润同方向变化=执行一致性
        if (rev_growth > 0 and ni_growth > 0) or (rev_growth <= 0 and ni_growth <= 0):
            consistent_years += 1
        total_years += 1

    consistency = safe_div(consistent_years, total_years)

    return {"raw": {"narrative_consistency": consistency}, "redline": None}
