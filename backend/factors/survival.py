# -*- coding: utf-8 -*-
"""生存力维度因子 S1-S6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_SURVIVAL
from backend.factors.helpers import get_fact_value, get_annual_values, safe_div, volatility


@register_factor("S1", DIM_SURVIVAL, "杠杆与偿债压力")
def compute_s1(db: Session, company_id: str, asof: date) -> dict:
    """S1: 利息保障倍数 & NetDebt/EBITDA"""
    # 美股用 EBITDA 相关概念，A股用对应字段
    op_income = get_fact_value(db, company_id, "OperatingIncomeLoss", asof) or \
                get_fact_value(db, company_id, "operating_income", asof)
    dep = get_fact_value(db, company_id, "DepreciationDepletionAndAmortization", asof) or \
          get_fact_value(db, company_id, "DepreciationAndAmortization", asof) or 0
    interest = get_fact_value(db, company_id, "InterestExpense", asof) or \
               get_fact_value(db, company_id, "interest_expense", asof)

    ebitda = (op_income + dep) if op_income else None
    interest_coverage = safe_div(ebitda, abs(interest)) if interest and interest != 0 else None

    total_debt = (get_fact_value(db, company_id, "LongTermDebt", asof) or
                  get_fact_value(db, company_id, "long_term_debt", asof) or 0) + \
                 (get_fact_value(db, company_id, "ShortTermBorrowings", asof) or
                  get_fact_value(db, company_id, "short_term_debt", asof) or 0)
    cash = get_fact_value(db, company_id, "CashAndCashEquivalentsAtCarryingValue", asof) or \
           get_fact_value(db, company_id, "cash", asof) or 0
    net_debt = total_debt - cash
    net_debt_ebitda = safe_div(net_debt, ebitda)

    # 红线检测
    redline = None
    if interest_coverage is not None and interest_coverage < 1.5:
        redline = "interest_coverage_below_1.5"
    if net_debt_ebitda is not None and net_debt_ebitda > 4:
        redline = "net_debt_ebitda_above_4"

    return {
        "raw": {"interest_coverage": interest_coverage, "net_debt_ebitda": net_debt_ebitda},
        "redline": redline,
    }


@register_factor("S2", DIM_SURVIVAL, "流动性缓冲")
def compute_s2(db: Session, company_id: str, asof: date) -> dict:
    """S2: 流动比率 & 现金比率"""
    current_assets = get_fact_value(db, company_id, "CurrentAssets", asof) or \
                     get_fact_value(db, company_id, "current_assets", asof)
    current_liab = get_fact_value(db, company_id, "CurrentLiabilities", asof) or \
                   get_fact_value(db, company_id, "current_liabilities", asof)
    cash = get_fact_value(db, company_id, "CashAndCashEquivalentsAtCarryingValue", asof) or \
           get_fact_value(db, company_id, "cash", asof)

    current_ratio = safe_div(current_assets, current_liab)
    cash_ratio = safe_div(cash, current_liab)

    return {"raw": {"current_ratio": current_ratio, "cash_ratio": cash_ratio}, "redline": None}


@register_factor("S3", DIM_SURVIVAL, "自由现金流韧性")
def compute_s3(db: Session, company_id: str, asof: date) -> dict:
    """S3: FCF Margin 及其波动"""
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    capex = get_fact_value(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", asof) or \
            get_fact_value(db, company_id, "capex_cash", asof) or 0
    revenue = get_fact_value(db, company_id, "Revenues", asof) or \
              get_fact_value(db, company_id, "RevenueFromContractWithCustomerExcludingAssessedTax", asof) or \
              get_fact_value(db, company_id, "revenue", asof)

    fcf = (ocf - abs(capex)) if ocf is not None else None
    fcf_margin = safe_div(fcf, revenue)

    # 历年波动
    ocf_series = get_annual_values(db, company_id, "NetCashProvidedByUsedInOperatingActivities", 5, asof) or \
                 get_annual_values(db, company_id, "ocf", 5, asof)
    vol = volatility(ocf_series) if ocf_series else None

    return {"raw": {"fcf": fcf, "fcf_margin": fcf_margin, "ocf_volatility": vol}, "redline": None}


@register_factor("S4", DIM_SURVIVAL, "盈利质量")
def compute_s4(db: Session, company_id: str, asof: date) -> dict:
    """S4: OCF / 净利润 一致性"""
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof)

    ocf_to_ni = safe_div(ocf, ni) if ni and ni != 0 else None

    return {"raw": {"ocf_to_ni": ocf_to_ni}, "redline": None}


@register_factor("S5", DIM_SURVIVAL, "融资稀释压力")
def compute_s5(db: Session, company_id: str, asof: date) -> dict:
    """S5: 三年股本变化率"""
    shares_series = get_annual_values(db, company_id, "CommonStockSharesOutstanding", 4, asof) or \
                    get_annual_values(db, company_id, "shares_outstanding_capital", 4, asof)

    dilution_3y = None
    if len(shares_series) >= 2:
        newest, oldest = shares_series[0], shares_series[-1]
        if oldest and oldest > 0:
            dilution_3y = (newest - oldest) / oldest

    redline = None
    if dilution_3y is not None and dilution_3y > 0.3:
        redline = "high_dilution_above_30pct"

    return {"raw": {"dilution_3y": dilution_3y}, "redline": redline}


@register_factor("S6", DIM_SURVIVAL, "重大风险事件红旗")
def compute_s6(db: Session, company_id: str, asof: date) -> dict:
    """S6: 风险事件（MVP 简化版：基于 filing 中 8-K 数量代理）"""
    from sqlalchemy import select, func, and_
    from backend.models import Filing
    from datetime import timedelta

    three_years_ago = asof - timedelta(days=365 * 3)
    count = db.execute(
        select(func.count(Filing.filing_id)).where(and_(
            Filing.company_id == company_id,
            Filing.form_type.in_(["8-K", "8-K/A"]),
            Filing.filed_date >= three_years_ago,
            Filing.filed_date <= asof,
        ))
    ).scalar() or 0

    return {"raw": {"risk_event_count_3y": count}, "redline": None}
