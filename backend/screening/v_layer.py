# -*- coding: utf-8 -*-
"""V-Layer 价格层（PRD 第 7 节）。

依赖 valuation_v1 落库的 pe_ttm 截面值。

输出 v_result dict：
{
  "v_state": "TooExpensive" | "Acceptable" | "Cheap" | None,
  "reason_codes": [...],
  "metrics": {"pe_ttm": ...},
}

裁决：
- pe_ttm 不存在或 ≤ 0（EPS≤0）→ v_state=None + V1_NEGATIVE_EPS
- valuation_mode == strict: pe ≤ 14.9 → Cheap；else TooExpensive
- valuation_mode == standard: 分级阈值
  - q_strong_track → ≤ 22 = Acceptable / ≤ 14.9 = Cheap
  - q_passed       → ≤ 18 = Acceptable / ≤ 14.9 = Cheap
  - 其他           → ≤ 15 = Acceptable / ≤ 14.9 = Cheap
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.metric_periodic import MetricPeriodic

from backend.screening.config import ScreenConfig
from backend.screening.reason_codes import (
    V1_NEGATIVE_EPS,
    V2_PASS_STRICT,
    V3_PASS_STANDARD,
    V_NO_PRICE,
    V_TOO_EXPENSIVE,
)


def _latest_valuation_metric(
    db: Session,
    company_id: str,
    metric_name: str,
    asof_date: date,
) -> Optional[float]:
    row = db.execute(
        select(MetricPeriodic.value)
        .where(
            and_(
                MetricPeriodic.company_id == company_id,
                MetricPeriodic.metric_name == metric_name,
                MetricPeriodic.formula_version == "valuation_v1",
                MetricPeriodic.period_end <= asof_date,
            )
        )
        .order_by(MetricPeriodic.period_end.desc())
        .limit(1)
    ).first()
    if row is None or row.value is None:
        return None
    return float(row.value)


def evaluate_v_layer(
    db: Session,
    company_id: str,
    asof_date: date,
    config: ScreenConfig,
    *,
    q_passed: bool = False,
    q_strong_track: bool = False,
) -> dict:
    reason_codes: list[str] = []
    metrics: dict[str, Optional[float]] = {}

    pe_ttm = _latest_valuation_metric(db, company_id, "pe_ttm", asof_date)
    market_cap = _latest_valuation_metric(db, company_id, "market_cap", asof_date)
    ev_ebit = _latest_valuation_metric(db, company_id, "ev_ebit", asof_date)
    metrics["pe_ttm"] = pe_ttm
    metrics["market_cap"] = market_cap
    metrics["ev_ebit"] = ev_ebit

    # 无价格或无 PE（EPS≤0）
    if pe_ttm is None or pe_ttm <= 0:
        if market_cap is None:
            reason_codes.append(V_NO_PRICE)
            return {"v_state": None, "reason_codes": reason_codes, "metrics": metrics}
        # 有市值但无 PE → EPS ≤ 0
        reason_codes.append(V1_NEGATIVE_EPS)
        return {"v_state": None, "reason_codes": reason_codes, "metrics": metrics}

    # ===== 严格模式 =====
    if config.valuation_mode == "strict":
        if pe_ttm <= config.v_pe_strict:
            reason_codes.append(V2_PASS_STRICT)
            return {"v_state": "Cheap", "reason_codes": reason_codes, "metrics": metrics}
        reason_codes.append(V_TOO_EXPENSIVE)
        return {"v_state": "TooExpensive", "reason_codes": reason_codes, "metrics": metrics}

    # ===== 标准 / 宽松模式 — 分级阈值 =====
    if q_strong_track:
        upper = config.v_pe_standard_top      # 22
    elif q_passed:
        upper = config.v_pe_standard_passed   # 18
    else:
        upper = config.v_pe_standard_other    # 15

    if pe_ttm <= config.v_pe_strict:
        reason_codes.append(V2_PASS_STRICT)
        return {"v_state": "Cheap", "reason_codes": reason_codes, "metrics": metrics}
    if pe_ttm <= upper:
        reason_codes.append(V3_PASS_STANDARD)
        return {"v_state": "Acceptable", "reason_codes": reason_codes, "metrics": metrics}

    reason_codes.append(V_TOO_EXPENSIVE)
    return {"v_state": "TooExpensive", "reason_codes": reason_codes, "metrics": metrics}
