# -*- coding: utf-8 -*-
"""复制力维度因子 R1-R6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_REPLICATION
from backend.factors.helpers import get_fact_value, get_annual_values, safe_div, cagr, volatility, get_revenue, get_revenue_series


def _calc_invested_capital(db: Session, company_id: str, asof: date) -> float | None:
    """计算投入资本 = 总资产 - 现金 - 无息流动负债（简化版: 总资产 - 现金 - 流动负债 + 短期借款）"""
    total_assets = get_fact_value(db, company_id, "Assets", asof) or \
                   get_fact_value(db, company_id, "total_assets", asof)
    cash = get_fact_value(db, company_id, "CashAndCashEquivalentsAtCarryingValue", asof) or \
           get_fact_value(db, company_id, "cash", asof) or 0
    current_liab = get_fact_value(db, company_id, "CurrentLiabilities", asof) or \
                   get_fact_value(db, company_id, "current_liabilities", asof) or 0
    short_debt = get_fact_value(db, company_id, "ShortTermBorrowings", asof) or \
                 get_fact_value(db, company_id, "short_term_debt", asof) or 0

    if total_assets is None:
        return None
    return total_assets - cash - current_liab + short_debt


def _calc_nopat(db: Session, company_id: str, asof: date) -> float | None:
    """NOPAT = 营业利润 × (1 - 有效税率)，简化版用 净利润 + 利息费用*(1-25%)"""
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof)
    interest = get_fact_value(db, company_id, "InterestExpense", asof) or \
               get_fact_value(db, company_id, "interest_expense", asof) or 0
    if ni is None:
        return None
    return ni + abs(interest) * 0.75  # 假设 25% 税率


@register_factor("R1", DIM_REPLICATION, "长期ROIC/ROCE水平")
def compute_r1(db: Session, company_id: str, asof: date) -> dict:
    """R1: 5年平均 ROIC"""
    roic_values = []
    for year_offset in range(5):
        from datetime import timedelta
        check_date = date(asof.year - year_offset, 12, 31)
        nopat = _calc_nopat(db, company_id, check_date)
        ic = _calc_invested_capital(db, company_id, check_date)
        roic = safe_div(nopat, ic)
        if roic is not None:
            roic_values.append(roic)

    avg_roic = sum(roic_values) / len(roic_values) if roic_values else None

    return {"raw": {"roic_5y_avg": avg_roic, "roic_count": len(roic_values)}, "redline": None}


@register_factor("R2", DIM_REPLICATION, "增量ROIC")
def compute_r2(db: Session, company_id: str, asof: date) -> dict:
    """R2: 增量 ROIC = (NOPAT_t - NOPAT_t-3) / (IC_t - IC_t-3)"""
    nopat_now = _calc_nopat(db, company_id, asof)
    ic_now = _calc_invested_capital(db, company_id, asof)
    past = date(asof.year - 3, 12, 31)
    nopat_past = _calc_nopat(db, company_id, past)
    ic_past = _calc_invested_capital(db, company_id, past)

    inc_roic = None
    if all(v is not None for v in [nopat_now, nopat_past, ic_now, ic_past]):
        delta_ic = ic_now - ic_past
        if delta_ic > 0:
            inc_roic = (nopat_now - nopat_past) / delta_ic

    return {"raw": {"inc_roic": inc_roic}, "redline": None}


@register_factor("R3", DIM_REPLICATION, "收入增长质量")
def compute_r3(db: Session, company_id: str, asof: date) -> dict:
    """R3: 5年收入 CAGR + 波动率"""
    rev_series = get_revenue_series(db, company_id, 6, asof)

    rev_cagr = cagr(rev_series) if len(rev_series) >= 2 else None
    rev_vol = volatility(rev_series) if len(rev_series) >= 3 else None

    return {"raw": {"rev_cagr_5y": rev_cagr, "rev_vol_5y": rev_vol}, "redline": None}


@register_factor("R4", DIM_REPLICATION, "毛利与成本结构")
def compute_r4(db: Session, company_id: str, asof: date) -> dict:
    """R4: 毛利率 + SGA 占比"""
    revenue = get_revenue(db, company_id, asof)
    gross_profit = get_fact_value(db, company_id, "GrossProfit", asof)
    sga = get_fact_value(db, company_id, "SellingGeneralAndAdministrativeExpense", asof)

    # A 股没有独立 GrossProfit，用 收入 - 营业成本 估算
    if gross_profit is None:
        total_cost = get_fact_value(db, company_id, "total_cost", asof)
        if revenue and total_cost:
            gross_profit = revenue - total_cost

    # A 股 SGA = 销售费用 + 管理费用
    if sga is None:
        selling = get_fact_value(db, company_id, "selling_expense", asof) or 0
        admin = get_fact_value(db, company_id, "admin_expense", asof) or 0
        sga = selling + admin if (selling or admin) else None

    gross_margin = safe_div(gross_profit, revenue)
    sga_ratio = safe_div(sga, revenue)

    return {"raw": {"gross_margin": gross_margin, "sga_ratio": sga_ratio}, "redline": None}


@register_factor("R5", DIM_REPLICATION, "资本配置质量")
def compute_r5(db: Session, company_id: str, asof: date) -> dict:
    """R5: 再投资率 + 回购/分红收益率"""
    capex = get_fact_value(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", asof) or \
            get_fact_value(db, company_id, "capex_cash", asof) or 0
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    dividends = get_fact_value(db, company_id, "PaymentsOfDividends", asof) or \
                get_fact_value(db, company_id, "dividends_and_interest_paid", asof) or 0
    buyback = get_fact_value(db, company_id, "PaymentsForRepurchaseOfCommonStock", asof) or 0

    reinvest_rate = safe_div(abs(capex), ocf) if ocf else None

    return {
        "raw": {"reinvest_rate": reinvest_rate, "dividends": dividends, "buyback": buyback},
        "redline": None,
    }


@register_factor("R6", DIM_REPLICATION, "成本高信号一致性")
def compute_r6(db: Session, company_id: str, asof: date) -> dict:
    """R6: 信号一致性 — 收入增长 vs 利润增长 vs FCF增长的方向一致性
    三个指标增长方向一致=高信号一致性=管理层说到做到
    """
    rev_series = get_revenue_series(db, company_id, 4, asof)
    ni_series = get_annual_values(db, company_id, "NetIncomeLoss", 4, asof) or \
                get_annual_values(db, company_id, "net_income", 4, asof)
    ocf_series = get_annual_values(db, company_id, "NetCashProvidedByUsedInOperatingActivities", 4, asof) or \
                 get_annual_values(db, company_id, "ocf", 4, asof)

    if len(rev_series) < 2 or len(ni_series) < 2 or len(ocf_series) < 2:
        return {"raw": {"signal_cost_score": None}, "redline": None}

    n = min(len(rev_series), len(ni_series), len(ocf_series))
    consistent = 0
    total = 0

    for i in range(n - 1):
        rev_up = rev_series[i] > rev_series[i + 1]
        ni_up = ni_series[i] > ni_series[i + 1]
        ocf_up = ocf_series[i] > ocf_series[i + 1]
        # 三个指标方向一致得1分，两个一致得0.5分
        votes = sum([rev_up, ni_up, ocf_up])
        if votes == 3 or votes == 0:  # 全涨或全跌
            consistent += 1.0
        else:
            consistent += 0.33
        total += 1

    score = consistent / total if total > 0 else None

    return {"raw": {"signal_cost_score": score}, "redline": None}
