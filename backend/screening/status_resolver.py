# -*- coding: utf-8 -*-
"""五状态裁决（PRD 第 8 节）。

| 状态 | 触发 |
|---|---|
| Rejected | Q0 排除 / Q3 不过（不含 Q5 / Q6）/ R 层硬 REJECT |
| Review | Q5 负营运资本 / Q6 上市过短 / R 层 REVIEW / RULE_ONLY 含软触发 |
| TooExpensive | Q 过 + R 通过 + V 太贵 |
| NearFairPrice | Q 过 + R 通过 + V 可接受（非强通过 或 非低估）|
| HighConviction | Q 强通过 + R 通过 + V Cheap |
"""
from __future__ import annotations

from backend.screening.reason_codes import (
    Q5_NEGATIVE_CAPITAL_EMPLOYED,
    Q6_LIST_DATE_TOO_RECENT,
)


def resolve_status(q_result: dict, r_result: dict, v_result: dict) -> str:
    """组合三层结果产出最终状态。"""
    q_passed = q_result["q_passed"]
    q_strong = q_result["q_strong_track"]
    r_action = r_result["r_action"]
    v_state = v_result["v_state"]
    q_codes = q_result.get("reason_codes", [])

    # Q 不通过的两种情况
    if not q_passed:
        # Q5 / Q6 → Review（PRD 要求人工覆核）
        if Q5_NEGATIVE_CAPITAL_EMPLOYED in q_codes or Q6_LIST_DATE_TOO_RECENT in q_codes:
            return "Review"
        return "Rejected"

    # Q 通过：看 R 层
    if r_action == "REJECT":
        return "Rejected"
    if r_action == "REVIEW":
        return "Review"

    # R PASS / RULE_ONLY / MONITOR：继续看 V 层
    # RULE_ONLY 含义是"AI 未启用或不可用，仅基于硬规则结果"，硬规则未触发即视为通过
    r_passed = r_action in ("PASS", "RULE_ONLY", "MONITOR")

    # V 无价格或 EPS≤0 → 暂归 Review（需关注）
    if v_state is None:
        return "Review"
    if v_state == "TooExpensive":
        return "TooExpensive"

    # 价格通过
    if q_strong and r_passed and v_state == "Cheap":
        return "HighConviction"
    return "NearFairPrice"
