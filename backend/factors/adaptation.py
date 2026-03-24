# -*- coding: utf-8 -*-
"""适应力维度因子 A1-A6"""
from datetime import date
from sqlalchemy.orm import Session

from backend.factors.registry import register_factor, DIM_ADAPTATION
from backend.factors.helpers import get_fact_value, get_annual_values, safe_div, volatility


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
    rev_series = get_annual_values(db, company_id, "Revenues", 5, asof) or \
                 get_annual_values(db, company_id, "revenue", 5, asof)
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
    revenue = get_fact_value(db, company_id, "Revenues", asof) or \
              get_fact_value(db, company_id, "revenue", asof)

    rd_ratio = safe_div(rd, revenue)

    return {"raw": {"rd_ratio": rd_ratio}, "redline": None}


@register_factor("A4", DIM_ADAPTATION, "客户/产品集中度风险")
def compute_a4(db: Session, company_id: str, asof: date) -> dict:
    """A4: MVP 简化版 — 使用收入波动作为集中度代理"""
    rev_series = get_annual_values(db, company_id, "Revenues", 5, asof) or \
                 get_annual_values(db, company_id, "revenue", 5, asof)
    rev_vol = volatility(rev_series) if len(rev_series) >= 3 else None

    return {"raw": {"concentration_proxy": rev_vol}, "redline": None}


@register_factor("A5", DIM_ADAPTATION, "治理与决策反应（AI）")
def compute_a5(db: Session, company_id: str, asof: date) -> dict:
    """A5: MVP 返回中性分，Phase 2 用 LLM 实现"""
    return {"raw": {"governance_score": None}, "redline": None, "stub": True}


@register_factor("A6", DIM_ADAPTATION, "监管适配与合规历史")
def compute_a6(db: Session, company_id: str, asof: date) -> dict:
    """A6: MVP 简化版 — 使用 filing 中特定类型计数"""
    return {"raw": {"reg_event_count_3y": None}, "redline": None, "stub": True}
