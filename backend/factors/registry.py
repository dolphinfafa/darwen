# -*- coding: utf-8 -*-
"""因子注册表：因子代码 → 计算函数映射"""
from typing import Callable

# 因子注册表：{factor_code: (compute_func, dimension, description)}
_REGISTRY: dict[str, tuple[Callable, str, str]] = {}


def register_factor(code: str, dimension: str, description: str = ""):
    """装饰器：注册因子计算函数"""
    def decorator(func: Callable):
        _REGISTRY[code] = (func, dimension, description)
        return func
    return decorator


def get_factor(code: str) -> tuple[Callable, str, str] | None:
    return _REGISTRY.get(code)


def get_all_factors() -> dict[str, tuple[Callable, str, str]]:
    return _REGISTRY.copy()


def get_factors_by_dimension(dimension: str) -> dict[str, tuple[Callable, str, str]]:
    return {k: v for k, v in _REGISTRY.items() if v[1] == dimension}


# 五大维度常量
DIM_SURVIVAL = "survival"
DIM_REPLICATION = "replication"
DIM_ADAPTATION = "adaptation"
DIM_MOAT = "moat"
DIM_VALUATION = "valuation"

ALL_DIMENSIONS = [DIM_SURVIVAL, DIM_REPLICATION, DIM_ADAPTATION, DIM_MOAT, DIM_VALUATION]
