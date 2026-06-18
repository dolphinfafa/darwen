# -*- coding: utf-8 -*-
"""Q-Layer 质量层 / ROCE 漏斗第一层。

按用户配置的回溯窗口 `roce_lookback_years`（N）从 metric_periodic 的逐年
`roce` 序列现算门槛，支持任意 N（3/5/7/10…）。判定口径：
- short 窗口 = 最近 N 个完整财年；通过要求 中位数 ≥ threshold 且 达标年数 ≥ ⌈0.8N⌉
- long  窗口 = 最近 2N 个完整财年；strong（Q4）= 有效年数 ≥ ⌈0.8·2N⌉ 且 中位数 ≥ threshold
- 近 N 年内 ≥ 2 年资本雇用为负/缺失 → Q5 人工覆核

设计要点：N=5 时与旧 `metrics.roce.evaluate_quality_gate` 的 5Y/10Y 口径完全等价
（short=5 达标 4、long=10 达标 8、缺失阈值 2），保证向后兼容。

输出 q_result dict：
{
  "q_passed": bool,
  "q_strong_track": bool,
  "reason_codes": [...],
  "metrics": {"roce_median": ..., "roce_5y_median": ..., "roce_10y_median": ...,
              "roce_lookback_years": N},
}
"""
from __future__ import annotations

import math
import statistics
from datetime import date
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


def _read_roce_series(
    db: Session,
    company_id: str,
    asof_date: date,
    formula_version: str = "roce_v1",
) -> list[tuple[date, Optional[float]]]:
    """读 metric_periodic 中 ≤ asof_date 的逐年 roce，每财年一条，按 period_end 升序返回。

    同一财年可能有多个 period_end（财年末月份变更/季度口径），按"回溯 N 个财年"语义
    须按日历年去重：每年保留 period_end 最大（最接近年末）的那条。
    """
    rows = db.execute(
        select(MetricPeriodic.period_end, MetricPeriodic.value)
        .where(
            and_(
                MetricPeriodic.company_id == company_id,
                MetricPeriodic.metric_name == "roce",
                MetricPeriodic.formula_version == formula_version,
                MetricPeriodic.period_end <= asof_date,
            )
        )
        .order_by(MetricPeriodic.period_end.asc())
    ).all()
    # 已按 period_end 升序：后写入覆盖前者 → 每年保留 period_end 最大的一条
    by_year: dict[int, tuple[date, Optional[float]]] = {}
    for r in rows:
        by_year[r.period_end.year] = (r.period_end, float(r.value) if r.value is not None else None)
    return [by_year[y] for y in sorted(by_year)]


def evaluate_roce_gate(
    roce_rows: list[tuple[date, Optional[float]]],
    *,
    threshold: float,
    lookback_years: int,
) -> dict:
    """纯函数：基于逐年 (period_end, roce) 升序序列，按 N 年窗口现算门槛判定。

    返回 {passed, strong, fail_reason, median_short, count_ge_short,
          n_valid_short, n_recent_short, median_long, n_valid_long, lookback_years}。
    fail_reason ∈ {None, Q1_INSUFFICIENT_HISTORY, Q5_RECENT_NEG_CAP_OR_MISSING,
                   Q3_FAIL_MEDIAN, Q3_FAIL_COUNT}。

    N=5 时与 metrics.roce.evaluate_quality_gate 的 5Y/10Y 口径等价。
    """
    n = max(1, int(lookback_years))
    count_required_short = math.ceil(0.8 * n)
    count_required_long = math.ceil(0.8 * 2 * n)

    recent_short = roce_rows[-n:]
    recent_long = roce_rows[-(2 * n):]
    valid_short = [v for _, v in recent_short if v is not None]
    valid_long = [v for _, v in recent_long if v is not None]

    n_recent_short = len(recent_short)
    n_valid_short = len(valid_short)
    n_valid_long = len(valid_long)

    median_short = statistics.median(valid_short) if valid_short else None
    median_long = statistics.median(valid_long) if valid_long else None
    count_ge_short = sum(1 for v in valid_short if v >= threshold)

    fail_reason: Optional[str] = None
    passed = False
    if n_recent_short < n:
        fail_reason = "Q1_INSUFFICIENT_HISTORY"
    elif (n_recent_short - n_valid_short) >= 2:
        # 近 N 年内 ≥ 2 年资本雇用为负/缺失 → 人工覆核
        fail_reason = "Q5_RECENT_NEG_CAP_OR_MISSING"
    else:
        median_ok = median_short is not None and median_short >= threshold
        count_ok = count_ge_short >= count_required_short
        passed = median_ok and count_ok
        if not passed:
            fail_reason = "Q3_FAIL_MEDIAN" if not median_ok else "Q3_FAIL_COUNT"

    strong = (n_valid_long >= count_required_long) and (
        median_long is not None and median_long >= threshold
    )

    return {
        "passed": passed,
        "strong": strong,
        "fail_reason": fail_reason,
        "median_short": median_short,
        "count_ge_short": count_ge_short,
        "n_valid_short": n_valid_short,
        "n_recent_short": n_recent_short,
        "median_long": median_long,
        "n_valid_long": n_valid_long,
        "lookback_years": n,
    }


def evaluate_q_layer(
    db: Session,
    company: Company,
    asof_date: date,
    config: ScreenConfig,
) -> dict:
    """ROCE 漏斗第一层（Q0 已由 exclusion 前置处理）。按 config.roce_lookback_years 现算。"""
    reason_codes: list[str] = []
    metrics: dict[str, Optional[float]] = {}

    # Q6: 上市未满 min_list_years 年
    if company.list_date:
        years_listed = (asof_date - company.list_date).days / 365.25
        if years_listed < config.min_list_years:
            return {
                "q_passed": False,
                "q_strong_track": False,
                "reason_codes": [Q6_LIST_DATE_TOO_RECENT],
                "metrics": metrics,
            }

    n = config.roce_lookback_years
    gate = evaluate_roce_gate(
        _read_roce_series(db, company.company_id, asof_date),
        threshold=config.roce_threshold,
        lookback_years=n,
    )

    # metrics：roce_median 为本次 N 年窗口中位数；同时保留 roce_5y_median/roce_10y_median 兼容旧前端
    metrics["roce_median"] = gate["median_short"]
    metrics["roce_lookback_years"] = float(n)
    metrics["roce_5y_median"] = gate["median_short"]
    metrics["roce_10y_median"] = gate["median_long"]

    fail_reason = gate["fail_reason"]
    if fail_reason == "Q1_INSUFFICIENT_HISTORY":
        reason_codes.append(Q1_INSUFFICIENT_HISTORY)
        return {"q_passed": False, "q_strong_track": False, "reason_codes": reason_codes, "metrics": metrics}
    if fail_reason == "Q5_RECENT_NEG_CAP_OR_MISSING":
        # Q5：不自动排除，由 status_resolver 判定走 Review
        reason_codes.append(Q5_NEGATIVE_CAPITAL_EMPLOYED)
        return {"q_passed": False, "q_strong_track": False, "reason_codes": reason_codes, "metrics": metrics}
    if fail_reason == "Q3_FAIL_MEDIAN":
        reason_codes.append(Q3_FAIL_MEDIAN)
        return {"q_passed": False, "q_strong_track": False, "reason_codes": reason_codes, "metrics": metrics}
    if fail_reason == "Q3_FAIL_COUNT":
        reason_codes.append(Q3_FAIL_COUNT)
        return {"q_passed": False, "q_strong_track": False, "reason_codes": reason_codes, "metrics": metrics}

    # Q3 通过
    reason_codes.append(Q3_PASS)
    strong = gate["strong"]
    if strong:
        reason_codes.append(Q4_STRONG_TRACK_RECORD)

    return {
        "q_passed": True,
        "q_strong_track": strong,
        "reason_codes": reason_codes,
        "metrics": metrics,
    }
