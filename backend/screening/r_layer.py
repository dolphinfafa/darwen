# -*- coding: utf-8 -*-
"""R-Layer 风险层（PRD 第 6 节）。

M3 阶段实现 P0 硬规则 R1-R3；R4-R12 需要 AI 判定（M4 接入），暂占位返回 PASS。

输入：metric_periodic 已落库的 leverage / cash_quality / dilution 指标。

输出 r_result dict：
{
  "r_action": "PASS" | "REVIEW" | "REJECT" | "MONITOR" | "RULE_ONLY",
  "reason_codes": [...],
  "metrics": {...},
  "hard_triggered": bool,  # 是否有硬规则触发（供 M4 AI 融合判定）
}

裁决逻辑（M3 简化版，M4 接入 AI 后由 ai/orchestrator.fuse_r_layer 取代）：
- 硬规则 REJECT 信号触发 → r_action=REJECT
- 软信号触发 → r_action=REVIEW
- 全部通过 → r_action=PASS（或 RULE_ONLY 当 enable_ai_risk_layer=False 时）
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.metric_periodic import MetricPeriodic

from backend.screening.config import ScreenConfig
from backend.screening.reason_codes import (
    R1_DETERIORATING_LIQUIDITY,
    R1_HIGH_LEVERAGE,
    R1_LOW_COVERAGE,
    R2_PERSISTENT_FCF_NEGATIVE,
    R2_POOR_CFO_NI,
    R3_HIGH_DILUTION,
    R_PASS,
    R_RULE_ONLY,
)


def _latest_section(
    db: Session,
    company_id: str,
    metric_name: str,
    formula_version: str,
    asof_date: date,
) -> Optional[float]:
    row = db.execute(
        select(MetricPeriodic.value)
        .where(
            and_(
                MetricPeriodic.company_id == company_id,
                MetricPeriodic.metric_name == metric_name,
                MetricPeriodic.formula_version == formula_version,
                MetricPeriodic.period_end <= asof_date,
            )
        )
        .order_by(MetricPeriodic.period_end.desc())
        .limit(1)
    ).first()
    if row is None or row.value is None:
        return None
    return float(row.value)


def _latest_n_years(
    db: Session,
    company_id: str,
    metric_name: str,
    formula_version: str,
    asof_date: date,
    n: int = 5,
) -> list[tuple[date, float]]:
    """取 metric 的最近 n 年时序（按 period_end DESC）。"""
    rows = db.execute(
        select(MetricPeriodic.period_end, MetricPeriodic.value)
        .where(
            and_(
                MetricPeriodic.company_id == company_id,
                MetricPeriodic.metric_name == metric_name,
                MetricPeriodic.formula_version == formula_version,
                MetricPeriodic.period_end <= asof_date,
                MetricPeriodic.value.isnot(None),
            )
        )
        .order_by(MetricPeriodic.period_end.desc())
        .limit(n)
    ).all()
    return [(r.period_end, float(r.value)) for r in rows]


def evaluate_r_layer(
    db: Session,
    company_id: str,
    asof_date: date,
    config: ScreenConfig,
    *,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
) -> dict:
    """跑 R1-R3 硬规则；若 config.enable_ai_risk_layer 则接 AI 风险层。"""
    reason_codes: list[str] = []
    metrics: dict[str, Optional[float]] = {}
    hard_reject_signals = 0
    soft_review_signals = 0

    # ===== R1: 财务脆弱性 =====
    nd_ebit_series = _latest_n_years(db, company_id, "net_debt_ebit", "leverage_v1", asof_date, 3)
    int_cov_series = _latest_n_years(db, company_id, "interest_coverage", "leverage_v1", asof_date, 3)
    cur_ratio_series = _latest_n_years(db, company_id, "current_ratio", "leverage_v1", asof_date, 3)

    if nd_ebit_series:
        latest_nd_ebit = nd_ebit_series[0][1]
        metrics["net_debt_ebit"] = latest_nd_ebit
        if latest_nd_ebit > config.r1_net_debt_ebit_max:
            reason_codes.append(R1_HIGH_LEVERAGE)
            hard_reject_signals += 1

    if int_cov_series:
        latest_int_cov = int_cov_series[0][1]
        metrics["interest_coverage"] = latest_int_cov
        if latest_int_cov < config.r1_interest_coverage_min:
            reason_codes.append(R1_LOW_COVERAGE)
            hard_reject_signals += 1

    # current_ratio < 1 且连续 2 年恶化（最新 < 上一年 < 再上一年）
    if len(cur_ratio_series) >= 2:
        metrics["current_ratio"] = cur_ratio_series[0][1]
        latest = cur_ratio_series[0][1]
        if latest < config.r1_current_ratio_min:
            # 检查连续恶化
            sorted_asc = list(reversed(cur_ratio_series))  # 早到晚
            deteriorating = all(
                sorted_asc[i + 1] < sorted_asc[i]
                for i in range(len(sorted_asc) - 1)
            )
            if deteriorating and len(sorted_asc) >= 2:
                reason_codes.append(R1_DETERIORATING_LIQUIDITY)
                soft_review_signals += 1

    # ===== R2: 利润质量差 =====
    cfo_ni_consec = _latest_section(db, company_id, "cfo_ni_5y_consec_below_07", "cash_quality_v1", asof_date)
    fcf_neg = _latest_section(db, company_id, "fcf_neg_5y_years", "cash_quality_v1", asof_date)

    if cfo_ni_consec is not None:
        metrics["cfo_ni_5y_consec_below_07"] = cfo_ni_consec
        if cfo_ni_consec >= config.r2_cfo_ni_consec_below_07_max:
            reason_codes.append(R2_POOR_CFO_NI)
            soft_review_signals += 1

    if fcf_neg is not None:
        metrics["fcf_neg_5y_years"] = fcf_neg
        if fcf_neg > config.r2_fcf_neg_5y_max:
            reason_codes.append(R2_PERSISTENT_FCF_NEGATIVE)
            soft_review_signals += 1

    # ===== R3: 高频稀释 =====
    share_cagr = _latest_section(db, company_id, "share_count_cagr_5y", "dilution_v1", asof_date)
    if share_cagr is not None:
        metrics["share_count_cagr_5y"] = share_cagr
        if share_cagr > config.r3_share_cagr_5y_max:
            # 还要看 ROCE 是否未改善 — P0 简化暂不判断 ROCE 趋势
            reason_codes.append(R3_HIGH_DILUTION)
            soft_review_signals += 1

    # ===== R4-R12: AI 风险层 =====
    ai_result_id: Optional[int] = None
    ai_overall: Optional[str] = None
    if config.enable_ai_risk_layer and user_id is not None:
        from backend.ai.orchestrator import analyze_risk, AIResult
        ai_outcome = analyze_risk(
            db,
            company_id=company_id,
            asof_date=asof_date,
            user_id=user_id,
            run_id=run_id,
            rule_triggered={
                "hard_triggered": hard_reject_signals > 0,
                "soft_triggered": soft_review_signals > 0,
                **{c: True for c in reason_codes},
            },
        )
        if isinstance(ai_outcome, AIResult):
            ai_result_id = ai_outcome.ai_result_id
            ai_overall = ai_outcome.overall_action
            # AI labels 加入 reason_codes
            for lbl in ai_outcome.output.labels:
                code = f"AI_{lbl.label.upper()}"
                if lbl.severity in ("high",):
                    code += "_HIGH"
                reason_codes.append(code)

    # ===== 裁决 =====
    if hard_reject_signals > 0:
        # R1 强信号：高杠杆 / 低利息保障 → REJECT（硬规则优先于 AI）
        r_action = "REJECT"
    elif ai_overall == "REJECT":
        r_action = "REJECT"
    elif ai_overall == "REVIEW" or soft_review_signals > 0:
        r_action = "REVIEW"
    elif ai_overall in ("PASS", "MONITOR"):
        r_action = ai_overall
    elif config.enable_ai_risk_layer:
        # AI 启用但调用失败 → RULE_ONLY
        r_action = "RULE_ONLY"
        if R_RULE_ONLY not in reason_codes:
            reason_codes.append(R_RULE_ONLY)
    else:
        # 未启用 AI → RULE_ONLY
        r_action = "RULE_ONLY"
        reason_codes.append(R_RULE_ONLY)

    if r_action == "PASS" and not reason_codes:
        reason_codes.append(R_PASS)

    return {
        "r_action": r_action,
        "reason_codes": reason_codes,
        "metrics": metrics,
        "hard_triggered": hard_reject_signals > 0,
        "ai_result_id": ai_result_id,
    }
