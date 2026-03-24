# -*- coding: utf-8 -*-
"""估值纪律维度因子 V1-V6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_VALUATION
from backend.factors.helpers import get_fact_value, get_annual_values, safe_div, cagr


@register_factor("V1", DIM_VALUATION, "同业估值分位")
def compute_v1(db: Session, company_id: str, asof: date) -> dict:
    """V1: PE/PB/FCF Yield（需要行情数据，MVP 先计算分母）"""
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof) or \
         get_fact_value(db, company_id, "net_income_to_parent", asof)
    equity = get_fact_value(db, company_id, "StockholdersEquity", asof) or \
             get_fact_value(db, company_id, "stockholders_equity", asof)
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    capex = get_fact_value(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", asof) or \
            get_fact_value(db, company_id, "capex_cash", asof) or 0
    fcf = (ocf - abs(capex)) if ocf else None

    return {
        "raw": {"earnings": ni, "book_value": equity, "fcf": fcf},
        "redline": None,
    }


@register_factor("V2", DIM_VALUATION, "质量调整安全边际")
def compute_v2(db: Session, company_id: str, asof: date) -> dict:
    """V2: 需要估值分位+质量分，评分引擎中计算"""
    return {"raw": {"mos_score": None}, "redline": None, "stub": True}


@register_factor("V3", DIM_VALUATION, "增长-估值匹配")
def compute_v3(db: Session, company_id: str, asof: date) -> dict:
    """V3: 收入/FCF 5年 CAGR"""
    rev_series = get_annual_values(db, company_id, "Revenues", 6, asof) or \
                 get_annual_values(db, company_id, "revenue", 6, asof)
    rev_cagr = cagr(rev_series) if len(rev_series) >= 2 else None

    return {"raw": {"rev_cagr_5y": rev_cagr}, "redline": None}


@register_factor("V4", DIM_VALUATION, "回撤买点")
def compute_v4(db: Session, company_id: str, asof: date) -> dict:
    """V4: 需要行情数据，MVP 简化"""
    return {"raw": {"drawdown_6m": None}, "redline": None, "stub": True}


@register_factor("V5", DIM_VALUATION, "估值红线")
def compute_v5(db: Session, company_id: str, asof: date) -> dict:
    """V5: 需要估值分位数据"""
    return {"raw": {"valuation_percentile": None}, "redline": None, "stub": True}


@register_factor("V6", DIM_VALUATION, "流动性与可交易性")
def compute_v6(db: Session, company_id: str, asof: date) -> dict:
    """V6: 需要行情数据计算 ADV"""
    return {"raw": {"adv_20": None}, "redline": None, "stub": True}
