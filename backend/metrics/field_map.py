# -*- coding: utf-8 -*-
"""字段映射：canonical 指标名 → 数据源 → concept 候选列表。

设计原则：
1. canonical 名是 Darwen 内部统一抽象，与具体数据源无关。
2. 每个 canonical 在每个 source_type 下提供按优先级排序的 concept 候选列表，
   helpers 按顺序回退查询（第一个命中即返回）。
3. SEC 字段使用 us-gaap taxonomy 实际 tag（如 OperatingIncomeLoss），
   存储在 fact.concept 字段（M1 重构时 account_code 退化为 "us-gaap"）。
4. TS-FS / AKSHARE 已 canonical 化，concept 即字段名（如 operating_income）。

字段覆盖范围：覆盖 ROCE / 杠杆 / 现金质量 / 稀释 / 估值五大类计算所需的全部输入。
"""
from __future__ import annotations

# 数据源优先级（按 company.market 路由）
SOURCE_PREFERENCE: dict[str, list[str]] = {
    "US": ["SEC"],
    "CN_A": ["TS-FS", "AKSHARE"],
}

# canonical 名 → source_type → [concept 候选列表]
# 候选列表按优先级排序，第一个命中即返回。
FIELD_MAP: dict[str, dict[str, list[str]]] = {
    # ===== 损益表 =====
    "revenue": {
        "SEC": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
        ],
        "TS-FS": ["revenue", "total_revenue"],
        "AKSHARE": ["revenue", "revenue_operating"],
    },
    "operating_income": {
        # EBIT 主源
        "SEC": ["OperatingIncomeLoss"],
        "TS-FS": ["operating_income"],
        "AKSHARE": ["operating_income"],
    },
    "ebit_reported": {
        # A 股有时直接披露 EBIT 字段；美股一般没有
        "SEC": [],
        "TS-FS": ["ebit"],
        "AKSHARE": [],
    },
    "total_profit": {
        # 利润总额：A 股 ROCE EBIT 终极回退用
        "SEC": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
        "TS-FS": ["total_profit"],
        "AKSHARE": [],
    },
    "interest_expense": {
        # 利息费用：用于 A 股 EBIT 回退公式 + R1 interest_coverage
        "SEC": ["InterestExpense", "InterestExpenseDebt"],
        "TS-FS": ["interest_expense", "finance_expense"],  # 财务费用近似（含利息净额）
        "AKSHARE": ["interest_expense", "finance_expense"],
    },
    "net_income": {
        "SEC": ["NetIncomeLoss"],
        "TS-FS": ["net_income", "net_income_to_parent"],
        "AKSHARE": ["net_income", "net_income_to_parent"],
    },

    # ===== 现金流量表 =====
    "cfo": {
        "SEC": ["NetCashProvidedByUsedInOperatingActivities"],
        "TS-FS": ["ocf"],
        "AKSHARE": ["ocf"],
    },
    "capex": {
        # 资本开支：FCF = CFO - CapEx
        "SEC": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "TS-FS": ["capex_cash"],  # TS-FS 未必有；fallback 用 fcf 推算
        "AKSHARE": ["capex_cash"],
    },
    "fcf_reported": {
        # Tushare 直接给 FCF
        "SEC": [],
        "TS-FS": ["fcf"],
        "AKSHARE": [],
    },

    # ===== 资产负债表：流动项 =====
    "current_assets": {
        "SEC": ["AssetsCurrent"],
        "TS-FS": ["current_assets"],
        "AKSHARE": ["current_assets"],
    },
    "current_liabilities": {
        "SEC": ["LiabilitiesCurrent"],
        "TS-FS": ["current_liabilities"],
        "AKSHARE": ["current_liabilities"],
    },
    "cash": {
        # ROCE 公式 OperatingCurrentAssets 需要扣减 cash
        "SEC": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
        "TS-FS": ["cash_and_equivalents"],
        "AKSHARE": ["cash"],
    },
    "short_term_investments": {
        # 缺失置 0，标 EXCESS_CASH_PROXY_LOW_CONFIDENCE
        "SEC": ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
        "TS-FS": ["short_term_investments"],
        "AKSHARE": [],  # AKSHARE 无明确字段，置 0
    },
    "short_term_debt": {
        # OperatingCurrentLiabilities 扣减项之一
        "SEC": ["ShortTermBorrowings", "CommercialPaper"],
        "TS-FS": ["short_term_debt"],
        "AKSHARE": ["short_term_debt"],
    },
    "current_portion_long_term_debt": {
        # OperatingCurrentLiabilities 扣减项之二
        "SEC": ["LongTermDebtCurrent"],
        "TS-FS": ["current_portion_ltd"],
        "AKSHARE": [],
    },
    "current_lease_liability": {
        # OperatingCurrentLiabilities 扣减项之三（缺失置 0）
        "SEC": ["OperatingLeaseLiabilityCurrent", "FinanceLeaseLiabilityCurrent"],
        "TS-FS": [],  # A 股 Tushare 未细拆
        "AKSHARE": [],
    },

    # ===== 资产负债表：长期项 =====
    "long_term_debt": {
        # R1 net_debt 计算
        "SEC": ["LongTermDebtNoncurrent", "LongTermDebt"],
        "TS-FS": ["long_term_debt"],
        "AKSHARE": ["long_term_debt"],
    },
    "net_ppe": {
        # ROCE CapitalEmployed 加项；剔除 goodwill/无形资产
        "SEC": ["PropertyPlantAndEquipmentNet"],
        "TS-FS": ["ppe_net"],
        "AKSHARE": ["ppe_net"],
    },
    "total_assets": {
        # R4 goodwill/assets 比率参考
        "SEC": ["Assets"],
        "TS-FS": ["total_assets"],
        "AKSHARE": ["total_assets"],
    },
    "total_liabilities": {
        "SEC": ["Liabilities"],
        "TS-FS": ["total_liabilities"],
        "AKSHARE": ["total_liabilities"],
    },
    "stockholders_equity": {
        "SEC": ["StockholdersEquity"],
        "TS-FS": ["stockholders_equity", "equity_to_parent"],
        "AKSHARE": ["stockholders_equity", "equity_to_parent"],
    },
    "goodwill": {
        # M3 R4 并购成瘾参考
        "SEC": ["Goodwill"],
        "TS-FS": ["goodwill"],
        "AKSHARE": ["goodwill"],
    },
    "intangible_assets": {
        "SEC": ["IntangibleAssetsNetExcludingGoodwill"],
        "TS-FS": ["intangible_assets"],
        "AKSHARE": ["intangible_assets"],
    },

    # ===== 股本 =====
    "shares_outstanding": {
        # M2.4 dilution & M2.5 pe_ttm
        # 优先 dei.EntityCommonStockSharesOutstanding（金融股真实股本）；
        # 多数公司 us-gaap.CommonStockSharesOutstanding 也有，二者并行兜底；
        # 加权流通股是周期均值，作末端 fallback
        "SEC": [
            "EntityCommonStockSharesOutstanding",
            "CommonStockSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic",
            "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        ],
        "TS-FS": ["shares_outstanding"],
        "AKSHARE": ["shares_outstanding_capital"],
    },
}


def candidate_concepts(canonical: str, source_type: str) -> list[str]:
    """返回 (canonical, source_type) 对应的 concept 候选列表。

    未注册的 canonical 或 source_type 返回空列表（调用方应判定为字段缺失）。
    """
    return FIELD_MAP.get(canonical, {}).get(source_type, [])


def all_canonicals() -> list[str]:
    """返回所有已注册的 canonical 名（用于回填/巡检）。"""
    return sorted(FIELD_MAP.keys())


def source_chain(market: str) -> list[str]:
    """按 market 返回数据源优先级链。"""
    return SOURCE_PREFERENCE.get(market, [])
