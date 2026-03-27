# -*- coding: utf-8 -*-
"""三套权重方案 + 因子维度内权重"""

# 维度权重方案（回测优化版 — 提高估值纪律权重以强化"好价格买好公司"）
DIMENSION_WEIGHTS = {
    "balanced": {
        "survival": 0.20,
        "replication": 0.20,
        "adaptation": 0.10,
        "moat": 0.25,
        "valuation": 0.25,
    },
    "conservative": {
        "survival": 0.25,
        "replication": 0.15,
        "adaptation": 0.10,
        "moat": 0.20,
        "valuation": 0.30,
    },
    "aggressive": {
        "survival": 0.15,
        "replication": 0.25,
        "adaptation": 0.15,
        "moat": 0.25,
        "valuation": 0.20,
    },
}

# 因子在维度内的权重（基准版，PRD 表四）
FACTOR_WEIGHTS = {
    "survival": {
        "S1": 0.18, "S2": 0.12, "S3": 0.12, "S4": 0.14, "S5": 0.10, "S6": 0.14,
        # S7 是工程项，不参与评分
    },
    "replication": {
        "R1": 0.20, "R2": 0.14, "R3": 0.14, "R4": 0.12, "R5": 0.20, "R6": 0.20,
    },
    "adaptation": {
        "A1": 0.18, "A2": 0.18, "A3": 0.14, "A4": 0.16, "A5": 0.18, "A6": 0.16,
    },
    "moat": {
        "M1": 0.18, "M2": 0.25, "M3": 0.10, "M4": 0.14, "M5": 0.08, "M6": 0.25,
    },
    "valuation": {
        "V1": 0.22, "V2": 0.20, "V3": 0.18, "V4": 0.12, "V5": 0.18, "V6": 0.10,
    },
}

# 分层阈值 — 使用分位数动态分层
# Top: 前 20%，Watch: 20%-60%，Reject: 后 40%
TIER_PERCENTILES = {
    "Top": 80,      # 总分 >= P80
    "Watch": 40,    # 总分 >= P40
    # < P40 → Reject
}

# 固定阈值（备选）
TIER_THRESHOLDS = {
    "Top": 65.0,
    "Watch": 45.0,
}

MODEL_NAMES = list(DIMENSION_WEIGHTS.keys())
