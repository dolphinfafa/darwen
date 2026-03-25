# -*- coding: utf-8 -*-
"""适应力维度因子 A1-A6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_ADAPTATION
from backend.factors.helpers import (
    get_fact_value, get_annual_values, safe_div, volatility,
    get_filing_count, get_revenue, get_revenue_series,
)


@register_factor("A1", DIM_ADAPTATION, "冲击期利润弹性")
def compute_a1(db: Session, company_id: str, asof: date) -> dict:
    """A1: 营业利润年度最大跌幅"""
    op_series = get_annual_values(db, company_id, "OperatingIncomeLoss", 6, asof) or \
                get_annual_values(db, company_id, "operating_income", 6, asof)

    max_drawdown = None
    if len(op_series) >= 2:
        drawdowns = []
        for i in range(len(op_series) - 1):
            if op_series[i + 1] and op_series[i + 1] > 0:
                dd = (op_series[i] - op_series[i + 1]) / abs(op_series[i + 1])
                drawdowns.append(dd)
        if drawdowns:
            max_drawdown = min(drawdowns)  # 最大跌幅（负数）

    return {"raw": {"shock_drawdown_op": max_drawdown}, "redline": None}


@register_factor("A2", DIM_ADAPTATION, "毛利稳定与传导能力")
def compute_a2(db: Session, company_id: str, asof: date) -> dict:
    """A2: 毛利率波动"""
    rev_series = get_revenue_series(db, company_id, 5, asof)
    gp_series = get_annual_values(db, company_id, "GrossProfit", 5, asof)

    # A 股估算毛利
    if not gp_series:
        cost_series = get_annual_values(db, company_id, "total_cost", 5, asof)
        if rev_series and cost_series and len(rev_series) == len(cost_series):
            gp_series = [r - c for r, c in zip(rev_series, cost_series)]

    gm_series = []
    if rev_series and gp_series:
        for r, g in zip(rev_series, gp_series):
            if r and r > 0 and g is not None:
                gm_series.append(g / r)

    gm_vol = volatility(gm_series) if len(gm_series) >= 3 else None

    return {"raw": {"gross_margin_stability": gm_vol}, "redline": None}


@register_factor("A3", DIM_ADAPTATION, "研发投入与效率")
def compute_a3(db: Session, company_id: str, asof: date) -> dict:
    """A3: 研发费用率"""
    rd = get_fact_value(db, company_id, "ResearchAndDevelopmentExpense", asof) or \
         get_fact_value(db, company_id, "rd_expense", asof)
    revenue = get_revenue(db, company_id, asof)

    rd_ratio = safe_div(rd, revenue)

    return {"raw": {"rd_ratio": rd_ratio}, "redline": None}


@register_factor("A4", DIM_ADAPTATION, "客户/产品集中度风险")
def compute_a4(db: Session, company_id: str, asof: date) -> dict:
    """A4: MVP 简化版 — 使用收入波动作为集中度代理"""
    rev_series = get_revenue_series(db, company_id, 5, asof)
    rev_vol = volatility(rev_series) if len(rev_series) >= 3 else None

    return {"raw": {"concentration_proxy": rev_vol}, "redline": None}


@register_factor("A5", DIM_ADAPTATION, "治理与决策反应")
def compute_a5(db: Session, company_id: str, asof: date) -> dict:
    """A5: 治理质量代理指标 — 基于可观测的财务治理信号
    - 股权稀释控制（低稀释=好治理）
    - 分红/回购回报股东意愿
    - 盈利质量（OCF/NI）
    综合得分 = (1 - dilution_rate) × ocf_ni_ratio × 有分红加分
    """
    # 股份稀释率（3年）
    shares_series = get_annual_values(db, company_id, "CommonStockSharesOutstanding", 4, asof) or \
                    get_annual_values(db, company_id, "WeightedAverageNumberOfShareOutstandingBasicAndDiluted", 4, asof)
    dilution_3y = None
    if len(shares_series) >= 2:
        oldest, newest = shares_series[-1], shares_series[0]
        if oldest and oldest > 0:
            dilution_3y = (newest - oldest) / oldest

    # OCF/NI 比率（盈利质量）
    ocf = get_fact_value(db, company_id, "NetCashProvidedByUsedInOperatingActivities", asof) or \
          get_fact_value(db, company_id, "ocf", asof)
    ni = get_fact_value(db, company_id, "NetIncomeLoss", asof) or \
         get_fact_value(db, company_id, "net_income", asof)
    ocf_ni = safe_div(ocf, ni) if ni and ni > 0 else None

    # 分红意愿
    dividends = get_fact_value(db, company_id, "PaymentsOfDividends", asof) or \
                get_fact_value(db, company_id, "dividends_and_interest_paid", asof)
    has_dividend = 1.0 if dividends and abs(dividends) > 0 else 0.0

    # 综合治理分
    gov_score = None
    components = []
    if dilution_3y is not None:
        components.append(max(0, 1.0 - abs(dilution_3y)))  # 稀释越少越好
    if ocf_ni is not None:
        components.append(min(ocf_ni, 2.0) / 2.0)  # OCF/NI 归一到 0-1
    if components:
        gov_score = sum(components) / len(components)
        gov_score = gov_score * (1.0 + 0.1 * has_dividend)  # 有分红加10%

    return {"raw": {"governance_score": gov_score}, "redline": None}


@register_factor("A6", DIM_ADAPTATION, "监管适配与合规历史")
def compute_a6(db: Session, company_id: str, asof: date) -> dict:
    """A6: 监管风险代理 — 用非常规 filing 数量衡量
    8-K（美股重大事件）越多=潜在监管/合规问题越多
    标准化为 3 年内 8-K 数量 / 平均水平
    """
    # 8-K 类 filing（美股重大事件披露）
    event_filings = get_filing_count(db, company_id, asof, form_types=["8-K", "8-K/A"], years=3)
    # 所有 filing
    total_filings = get_filing_count(db, company_id, asof, years=3)

    # 事件 filing 占比（越低=合规越好）
    if total_filings > 0:
        event_ratio = event_filings / total_filings
    elif event_filings == 0:
        event_ratio = 0.0  # 无任何 filing，按中性处理
    else:
        event_ratio = None

    return {"raw": {"reg_event_ratio_3y": event_ratio}, "redline": None}
