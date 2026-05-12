# -*- coding: utf-8 -*-
"""回测评估指标工具函数。"""
from __future__ import annotations

import math
import statistics
from typing import Sequence


def total_return(start: float, end: float) -> float:
    """简单总回报 (end / start) - 1。"""
    if start is None or end is None or start <= 0:
        return float("nan")
    return end / start - 1.0


def cagr(start_value: float, end_value: float, years: float) -> float:
    """复合年化收益率。"""
    if start_value is None or end_value is None or start_value <= 0 or years <= 0:
        return float("nan")
    return (end_value / start_value) ** (1.0 / years) - 1.0


def annualize_return(total_ret: float, years: float) -> float:
    """从总回报反推 CAGR。"""
    if total_ret is None or years <= 0:
        return float("nan")
    return (1.0 + total_ret) ** (1.0 / years) - 1.0


def safe_mean(values: Sequence[float]) -> float:
    vs = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.mean(vs) if vs else float("nan")


def safe_median(values: Sequence[float]) -> float:
    vs = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.median(vs) if vs else float("nan")


def win_rate(returns: Sequence[float], threshold: float = 0.0) -> float:
    """胜率：return > threshold 的比例。"""
    vs = [v for v in returns if v is not None and not math.isnan(v)]
    if not vs:
        return float("nan")
    return sum(1 for r in vs if r > threshold) / len(vs)


def quantile(values: Sequence[float], q: float) -> float:
    vs = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vs:
        return float("nan")
    n = len(vs)
    idx = max(0, min(n - 1, int(q * (n - 1))))
    return vs[idx]
