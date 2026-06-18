# -*- coding: utf-8 -*-
"""evaluate_roce_gate 纯函数单测。

重点：
1. 任意 N 年窗口现算（3/5/7）的通过/失败分支。
2. N=5 时与旧 metrics.roce.evaluate_quality_gate 的 5Y/10Y 口径等价（向后兼容护栏）。

纯函数测试，不依赖数据库。
"""
from datetime import date

from backend.metrics.roce import RoceComponents, evaluate_quality_gate
from backend.screening.q_layer import evaluate_roce_gate

THRESHOLD = 0.20


def _rows(values, start_year=2008):
    """[(period_end, roce)] 升序；values 中 None 表示该年无效。"""
    return [(date(start_year + i, 12, 31), v) for i, v in enumerate(values)]


def _components(values, start_year=2008):
    """构造旧 evaluate_quality_gate 所需的 RoceComponents 升序序列。"""
    out = []
    for i, v in enumerate(values):
        out.append(RoceComponents(year=start_year + i, period_end=date(start_year + i, 12, 31),
                                  market="US", roce=v))
    return out


# ---------- N 年现算：通过/失败分支 ----------

def test_n5_all_pass():
    g = evaluate_roce_gate(_rows([0.25] * 5), threshold=THRESHOLD, lookback_years=5)
    assert g["passed"] is True
    assert g["fail_reason"] is None


def test_n3_pass():
    # N=3：达标要求 ceil(0.8*3)=3
    g = evaluate_roce_gate(_rows([0.30, 0.30, 0.30]), threshold=THRESHOLD, lookback_years=3)
    assert g["passed"] is True


def test_n7_pass():
    # N=7：达标要求 ceil(0.8*7)=6，给 7 年达标
    g = evaluate_roce_gate(_rows([0.25] * 7), threshold=THRESHOLD, lookback_years=7)
    assert g["passed"] is True


def test_insufficient_history_q1():
    g = evaluate_roce_gate(_rows([0.25] * 4), threshold=THRESHOLD, lookback_years=5)
    assert g["passed"] is False
    assert g["fail_reason"] == "Q1_INSUFFICIENT_HISTORY"


def test_recent_neg_cap_q5():
    # 近 5 年内 2 年缺失（None）→ Q5 人工覆核
    g = evaluate_roce_gate(_rows([0.25, None, None, 0.25, 0.25]), threshold=THRESHOLD, lookback_years=5)
    assert g["passed"] is False
    assert g["fail_reason"] == "Q5_RECENT_NEG_CAP_OR_MISSING"


def test_fail_median():
    g = evaluate_roce_gate(_rows([0.10] * 5), threshold=THRESHOLD, lookback_years=5)
    assert g["passed"] is False
    assert g["fail_reason"] == "Q3_FAIL_MEDIAN"


def test_fail_count():
    # 中位数达标但达标年数不足（5 年中仅 3 年 ≥ 0.2，要求 4）
    g = evaluate_roce_gate(_rows([0.25, 0.25, 0.25, 0.10, 0.10]), threshold=THRESHOLD, lookback_years=5)
    assert g["passed"] is False
    assert g["fail_reason"] == "Q3_FAIL_COUNT"


def test_strong_track_needs_long_window():
    # 仅 5 年数据，N=5：long=10 窗口只有 5 个有效 < 8 → strong False
    g5 = evaluate_roce_gate(_rows([0.25] * 5), threshold=THRESHOLD, lookback_years=5)
    assert g5["strong"] is False
    # 10 年全达标 → strong True
    g10 = evaluate_roce_gate(_rows([0.25] * 10), threshold=THRESHOLD, lookback_years=5)
    assert g10["strong"] is True


# ---------- N=5 与旧 evaluate_quality_gate 等价性 ----------

import pytest


@pytest.mark.parametrize("values", [
    [0.25] * 10,                                  # 全通过 + strong
    [0.25] * 5,                                   # 5 年通过、非 strong
    [0.10] * 5,                                   # FAIL_MEDIAN
    [0.25, 0.25, 0.25, 0.10, 0.10],               # FAIL_COUNT
    [0.25, None, None, 0.25, 0.25],               # Q5
    [0.25] * 4,                                    # Q1
    [0.30, 0.10, 0.25, 0.22, 0.21, 0.26, 0.28, 0.24, 0.23, 0.27],  # 混合
])
def test_n5_equivalent_to_quality_gate(values):
    new = evaluate_roce_gate(_rows(values), threshold=THRESHOLD, lookback_years=5)
    old = evaluate_quality_gate(_components(values), threshold=THRESHOLD)
    assert new["passed"] == old.pass_5y_gate
    assert new["strong"] == old.strong_track_record
    assert new["fail_reason"] == old.fail_reason
