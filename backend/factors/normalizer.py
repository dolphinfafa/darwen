# -*- coding: utf-8 -*-
"""因子归一化：同市场×同行业×市值桶的分位数归一化（P5-P95）"""
import numpy as np


def percentile_normalize(
    value: float | None,
    universe_values: list[float],
    p_low: float = 5.0,
    p_high: float = 95.0,
) -> float | None:
    """
    分位数归一化到 0-100。
    value 在 universe_values 中的分位数位置，P5-P95 线性缩放，截尾。
    """
    if value is None or not universe_values:
        return None

    arr = np.array(universe_values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return 50.0  # 样本不足给中性分

    low = np.percentile(arr, p_low)
    high = np.percentile(arr, p_high)

    if high == low:
        return 50.0

    # 线性缩放到 0-100
    score = (value - low) / (high - low) * 100.0
    return float(np.clip(score, 0.0, 100.0))


def rank_normalize(value: float | None, universe_values: list[float]) -> float | None:
    """排名归一化到 0-100"""
    if value is None or not universe_values:
        return None

    arr = sorted(universe_values)
    n = len(arr)
    if n < 2:
        return 50.0

    # 找到 value 的排名
    rank = sum(1 for v in arr if v <= value)
    return (rank / n) * 100.0
