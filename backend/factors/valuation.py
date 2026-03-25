# -*- coding: utf-8 -*-
"""估值纪律维度因子 V1-V6"""
from datetime import date
import numpy as np
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_VALUATION
from backend.factors.helpers import (
    get_fact_value, get_annual_values, safe_div, cagr,
    get_close_prices, get_volume_series, get_revenue_series,
)


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
    """V2: 质量调整安全边际 = FCF Yield × 质量因子代理
    质量因子代理 = (ROIC + 毛利率) / 2 的归一化值
    FCF Yield 越高 + 质量越好 = 安全边际越大
    """
    # FCF yield 代理：FCF / Book Value（无市值时用账面值）
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    capex = get_fact_value(db, company_id, "PaymentsToAcquirePropertyPlantAndEquipment", asof) or \
            get_fact_value(db, company_id, "capex_cash", asof) or 0
    equity = get_fact_value(db, company_id, "StockholdersEquity", asof) or \
             get_fact_value(db, company_id, "stockholders_equity", asof)
    fcf = (ocf - abs(capex)) if ocf else None
    fcf_yield = safe_div(fcf, equity) if equity and equity > 0 else None

    # 质量代理：ROIC
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof)
    total_assets = get_fact_value(db, company_id, "Assets", asof) or \
                   get_fact_value(db, company_id, "total_assets", asof)
    roa = safe_div(ni, total_assets)

    # 综合安全边际分 = FCF Yield × (1 + ROA)
    mos_score = None
    if fcf_yield is not None and roa is not None:
        mos_score = fcf_yield * (1.0 + max(roa, 0))
    elif fcf_yield is not None:
        mos_score = fcf_yield

    return {"raw": {"mos_score": mos_score, "fcf_yield": fcf_yield, "roa": roa}, "redline": None}


@register_factor("V3", DIM_VALUATION, "增长-估值匹配(含动量)")
def compute_v3(db: Session, company_id: str, asof: date) -> dict:
    """V3: 收入 CAGR + 价格动量（12-1 momentum）
    动量 = 12 个月收益率排除最近 1 个月
    综合分 = 基本面增长 + 价格动量
    """
    rev_series = get_revenue_series(db, company_id, 6, asof)
    rev_cagr = cagr(rev_series) if len(rev_series) >= 2 else None

    # 12-1 动量
    prices = get_close_prices(db, company_id, asof, days=260)  # ~12个月
    momentum_12_1 = None
    if len(prices) >= 230:
        # 排除最近 1 个月（~21 交易日）
        p_start = prices[0][1]
        p_end = prices[-22][1] if len(prices) > 22 else prices[-1][1]
        if p_start and p_start > 0:
            momentum_12_1 = (p_end / p_start) - 1.0

    # 综合：有动量取动量，否则用基本面
    combined = None
    if rev_cagr is not None and momentum_12_1 is not None:
        combined = 0.5 * rev_cagr + 0.5 * momentum_12_1
    elif momentum_12_1 is not None:
        combined = momentum_12_1
    elif rev_cagr is not None:
        combined = rev_cagr

    return {"raw": {"growth_momentum": combined, "rev_cagr_5y": rev_cagr, "momentum_12_1": momentum_12_1}, "redline": None}


@register_factor("V4", DIM_VALUATION, "回撤买点")
def compute_v4(db: Session, company_id: str, asof: date) -> dict:
    """V4: 6 个月最大回撤 — 回撤越深越有买点（higher_better 逻辑反转）
    返回负值：-0.20 表示回撤 20%，值越大（接近0）说明没跌，值越小说明跌的多
    评分时 direction = higher_better，所以跌的少分高（安全），跌的多分低
    但实际逻辑是"回撤深=买点好"，因此在 FACTOR_DIRECTION 中设为 lower_better
    """
    prices = get_close_prices(db, company_id, asof, days=130)  # ~6个月交易日
    if len(prices) < 20:
        return {"raw": {"drawdown_6m": None}, "redline": None}

    close_arr = [p[1] for p in prices]
    # 计算最大回撤
    peak = close_arr[0]
    max_dd = 0.0
    for price in close_arr:
        if price > peak:
            peak = price
        dd = (price - peak) / peak
        if dd < max_dd:
            max_dd = dd

    return {"raw": {"drawdown_6m": max_dd}, "redline": None}


@register_factor("V5", DIM_VALUATION, "估值红线")
def compute_v5(db: Session, company_id: str, asof: date) -> dict:
    """V5: 估值安全度 — 用 P/E 倒数（Earnings Yield）表示
    Earnings Yield 越高=估值越便宜=越安全
    如果 Earnings Yield 极低（PE 极高），触发估值红线
    """
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof) or \
         get_fact_value(db, company_id, "net_income_to_parent", asof)
    equity = get_fact_value(db, company_id, "StockholdersEquity", asof) or \
             get_fact_value(db, company_id, "stockholders_equity", asof)

    # Earnings Yield 代理：NI / Book Equity
    earnings_yield = safe_div(ni, equity) if equity and equity > 0 else None

    # 红线：ROE < 0（亏损） 且 连续亏损
    redline = None
    if earnings_yield is not None and earnings_yield < -0.10:
        # 检查是否连续亏损
        ni_series = get_annual_values(db, company_id, "NetIncomeLoss", 3, asof) or \
                    get_annual_values(db, company_id, "net_income", 3, asof)
        if len(ni_series) >= 2 and all(v < 0 for v in ni_series[:2]):
            redline = "consecutive_loss_with_negative_roe"

    return {
        "raw": {"valuation_safety": earnings_yield},
        "redline": redline,
    }


@register_factor("V6", DIM_VALUATION, "流动性与可交易性")
def compute_v6(db: Session, company_id: str, asof: date) -> dict:
    """V6: 20 日平均成交量（ADV）"""
    volumes = get_volume_series(db, company_id, asof, days=20)
    adv_20 = float(np.mean(volumes)) if len(volumes) >= 5 else None

    return {"raw": {"adv_20": adv_20}, "redline": None}
