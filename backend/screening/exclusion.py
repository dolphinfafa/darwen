# -*- coding: utf-8 -*-
"""Q0 非适用证券排除（PRD 第 5 节）。

排除：金融、保险、券商、REIT、ETF、基金、SPAC、ADR、优先股、权证、壳公司、其他。
依据：company.instrument_type 字段。
另外 company.is_excluded=True（管理员手动标记）也排除。
"""
from __future__ import annotations

from typing import Optional

from backend.models.company import Company

from backend.screening.reason_codes import (
    Q0_BY_INSTRUMENT_TYPE,
    Q0_EXCLUDED_FLAG,
)


# 默认排除的 instrument_type 集合
_EXCLUDED_TYPES = frozenset(Q0_BY_INSTRUMENT_TYPE.keys())


def evaluate_q0(company: Company) -> Optional[str]:
    """返回 Q0 排除的 reason_code，若不排除则返回 None。"""
    if company.is_excluded:
        return Q0_EXCLUDED_FLAG
    if company.instrument_type in _EXCLUDED_TYPES:
        return Q0_BY_INSTRUMENT_TYPE[company.instrument_type]
    return None
