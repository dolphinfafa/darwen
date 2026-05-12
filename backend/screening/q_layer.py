# -*- coding: utf-8 -*-
"""Q-Layer 质量层（PRD 第 5 节）。

依赖 metric_periodic 表已落库的 ROCE 截面指标：
- roce_5y_median / roce_10y_median
- q3_pass_5y / q4_strong_track_record （notes 字段携带 fail_reason）

输出 q_result dict：
{
  "q_passed": bool,
  "q_strong_track": bool,
  "reason_codes": [...],
  "metrics": {"roce_5y_median": ..., "roce_10y_median": ...},
}
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.metric_periodic import MetricPeriodic

from backend.screening.config import ScreenConfig
from backend.screening.reason_codes import (
    Q1_INSUFFICIENT_HISTORY,
    Q3_FAIL_COUNT,
    Q3_FAIL_MEDIAN,
    Q3_PASS,
    Q4_STRONG_TRACK_RECORD,
    Q5_NEGATIVE_CAPITAL_EMPLOYED,
    Q6_LIST_DATE_TOO_RECENT,
)


def _read_section_metric(
    db: Session,
    company_id: str,
    metric_name: str,
    asof_date: date,
    formula_version: str = "roce_v1",
) -> tuple[Optional[float], Optional[str]]:
    """读 metric_periodic 中 ≤ asof_date 的最新截面 metric，返回 (value, notes)。"""
    row = db.execute(
        select(MetricPeriodic.value, MetricPeriodic.notes)
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
    if row is None:
        return None, None
    return (float(row.value) if row.value is not None else None, row.notes)


def evaluate_q_layer(
    db: Session,
    company: Company,
    asof_date: date,
    config: ScreenConfig,
) -> dict:
    """逐项执行 Q1-Q6（Q0 已由 exclusion 模块前置处理）。"""
    reason_codes: list[str] = []
    metrics: dict[str, Optional[float]] = {}

    # Q6: 上市未满 5 年
    if company.list_date:
        years_listed = (asof_date - company.list_date).days / 365.25
        if years_listed < config.min_list_years:
            return {
                "q_passed": False,
                "q_strong_track": False,
                "reason_codes": [Q6_LIST_DATE_TOO_RECENT],
                "metrics": metrics,
            }

    # 读 ROCE 截面 + fail_reason
    roce_5y, q3_notes = _read_section_metric(db, company.company_id, "roce_5y_median", asof_date)
    roce_10y, _ = _read_section_metric(db, company.company_id, "roce_10y_median", asof_date)
    q3_value, _ = _read_section_metric(db, company.company_id, "q3_pass_5y", asof_date)
    q4_value, _ = _read_section_metric(db, company.company_id, "q4_strong_track_record", asof_date)

    metrics["roce_5y_median"] = roce_5y
    metrics["roce_10y_median"] = roce_10y

    if q3_value is None:
        # 完全无截面数据（公司过新或字段缺）
        reason_codes.append(Q1_INSUFFICIENT_HISTORY)
        return {
            "q_passed": False,
            "q_strong_track": False,
            "reason_codes": reason_codes,
            "metrics": metrics,
        }

    # 解析 fail_reason（roce_v1 在 notes 字段携带 Q1/Q3/Q5 失败原因）
    fail_reason = q3_notes
    if fail_reason == "Q1_INSUFFICIENT_HISTORY":
        reason_codes.append(Q1_INSUFFICIENT_HISTORY)
        return {
            "q_passed": False,
            "q_strong_track": False,
            "reason_codes": reason_codes,
            "metrics": metrics,
        }
    if fail_reason == "Q5_RECENT_NEG_CAP_OR_MISSING":
        reason_codes.append(Q5_NEGATIVE_CAPITAL_EMPLOYED)
        # PRD Q5：不自动排除，进入人工覆核（status=Review）
        # 这里返回 q_passed=False 但 reason_codes 带 Q5，由 status_resolver 判定走 Review
        return {
            "q_passed": False,
            "q_strong_track": False,
            "reason_codes": reason_codes,
            "metrics": metrics,
        }
    if fail_reason == "Q3_FAIL_MEDIAN":
        reason_codes.append(Q3_FAIL_MEDIAN)
        return {
            "q_passed": False,
            "q_strong_track": False,
            "reason_codes": reason_codes,
            "metrics": metrics,
        }
    if fail_reason == "Q3_FAIL_COUNT":
        reason_codes.append(Q3_FAIL_COUNT)
        return {
            "q_passed": False,
            "q_strong_track": False,
            "reason_codes": reason_codes,
            "metrics": metrics,
        }

    # 走到这里说明 Q3 通过
    if q3_value >= 1.0:
        reason_codes.append(Q3_PASS)
    strong = q4_value is not None and q4_value >= 1.0
    if strong:
        reason_codes.append(Q4_STRONG_TRACK_RECORD)

    return {
        "q_passed": True,
        "q_strong_track": strong,
        "reason_codes": reason_codes,
        "metrics": metrics,
    }
