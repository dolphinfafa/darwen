# -*- coding: utf-8 -*-
"""ROCE 严格口径计算（PRD 第 4 节）。

公式：
    ROCE_t = EBIT_t / CapitalEmployed_t
    CapitalEmployed_t = NetWorkingCapitalExcessCash_t + NetFixedAssets_t
    NetWorkingCapitalExcessCash_t = OperatingCurrentAssets_t - OperatingCurrentLiabilities_t

其中：
    OperatingCurrentAssets_t = CurrentAssets - Cash - ShortTermInvestments
    OperatingCurrentLiabilities_t = CurrentLiabilities - ShortTermDebt
                                    - CurrentPortionLongTermDebt - CurrentLeaseLiability
    NetFixedAssets_t = Net PPE 仅（剔除 goodwill / 长期股权投资 / 无形资产 / 金融资产）

EBIT 取值优先级：
    US:   OperatingIncomeLoss
    CN_A: ebit_reported → operating_income + interest_expense → total_profit + interest_expense

降级标签（notes）：
    EXCESS_CASH_PROXY_LOW_CONFIDENCE  短期投资缺失置 0
    NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED 不自动排除，roce 设为 None
    EBIT_FROM_OP_INC_PLUS_INTEREST    A 股回退
    EBIT_FROM_TOTAL_PROFIT_PLUS_INTEREST
    EBIT_NOT_AVAILABLE / WORKING_CAPITAL_INCOMPLETE / PPE_MISSING
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from backend.metrics.helpers import (
    FactValue,
    _get_market,
    get_annual_periods,
    get_fiscal_year_end,
)


# 公式版本，每次口径调整都要 bump，metric_periodic 表按版本去重
FORMULA_VERSION = "roce_v1"


@dataclass
class RoceComponents:
    """单年 ROCE 计算结果及全部输入分量，用于落库 + 血缘日志。"""
    year: int
    period_end: Optional[date]
    market: str

    ebit: Optional[float] = None
    operating_current_assets: Optional[float] = None
    operating_current_liabilities: Optional[float] = None
    nwc_ex_cash: Optional[float] = None
    net_ppe: Optional[float] = None
    capital_employed: Optional[float] = None
    roce: Optional[float] = None

    notes: list[str] = field(default_factory=list)
    # field_name → fact_id（None 表示该输入缺失置 0）
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """是否产生了有效 ROCE 数值（capital_employed > 0 且分母分子都存在）。"""
        return self.roce is not None


@dataclass
class QualityGate:
    """5Y/10Y ROCE 质量门槛判定结果。

    与 PRD 第 4 节工程化判定一致：
    - pass_5y_gate: 5Y ROCE 中位数 ≥ threshold 且 5 年中至少 count_5y 年 ROCE ≥ threshold
    - strong_track_record: 10Y 可得 ≥ 8 年 且 10Y 中位数 ≥ threshold
    """
    n_valid_years: int  # 实际可得 ROCE 年数（5Y 窗口内）
    n_valid_10y: int    # 10Y 窗口内可得年数
    median_5y: Optional[float]
    median_10y: Optional[float]
    count_ge_threshold_5y: int
    pass_5y_gate: bool
    strong_track_record: bool
    fail_reason: Optional[str] = None  # Q1_INSUFFICIENT_HISTORY / Q3_FAIL_MEDIAN / Q3_FAIL_COUNT


# 各分量字段需要的 canonical 名
_NUMERATOR_FIELDS_US = ("operating_income",)
_NUMERATOR_FIELDS_CN = (
    "ebit_reported",
    "operating_income",
    "interest_expense",
    "total_profit",
)
_DENOMINATOR_FIELDS = (
    "current_assets",
    "current_liabilities",
    "cash",
    "short_term_investments",
    "short_term_debt",
    "current_portion_long_term_debt",
    "current_lease_liability",
    "net_ppe",
)


def _bulk_fetch(
    db: Session,
    company_id: str,
    canonicals: tuple[str, ...],
    year_range: tuple[int, int],
    market: str,
    fy_end_month: Optional[int],
) -> dict[str, dict[int, FactValue]]:
    """批量预拉所有 canonical 的多年数据，返回 {canonical: {year: FactValue}}。"""
    out: dict[str, dict[int, FactValue]] = {}
    for canonical in canonicals:
        series = get_annual_periods(
            db,
            company_id,
            canonical,
            year_range,
            market=market,
            fiscal_year_end_month=fy_end_month,
        )
        out[canonical] = {fv.period_end.year: fv for fv in series if fv.period_end}
    return out


def _resolve_ebit(
    year: int,
    market: str,
    cache: dict[str, dict[int, FactValue]],
    fact_ids: dict[str, Optional[str]],
    notes: list[str],
) -> Optional[float]:
    """按 PRD 优先级解析 EBIT。命中即填充 fact_ids 与 notes。"""
    if market == "US":
        fv = cache.get("operating_income", {}).get(year)
        if fv and fv.value is not None:
            fact_ids["ebit"] = fv.fact_id
            return fv.value
        return None

    # CN_A
    # 1. 直接 EBIT 字段
    fv = cache.get("ebit_reported", {}).get(year)
    if fv and fv.value is not None:
        fact_ids["ebit"] = fv.fact_id
        return fv.value

    # 2. 营业利润 + 利息费用
    op = cache.get("operating_income", {}).get(year)
    ie = cache.get("interest_expense", {}).get(year)
    if op and op.value is not None:
        ie_value = ie.value if (ie and ie.value is not None) else 0.0
        fact_ids["ebit_operating_income"] = op.fact_id
        fact_ids["ebit_interest_expense"] = ie.fact_id if (ie and ie.value is not None) else None
        notes.append("EBIT_FROM_OP_INC_PLUS_INTEREST")
        if ie is None or ie.value is None:
            notes.append("EBIT_INTEREST_EXPENSE_MISSING_ZEROED")
        return op.value + ie_value

    # 3. 利润总额 + 利息费用
    tp = cache.get("total_profit", {}).get(year)
    if tp and tp.value is not None:
        ie_value = ie.value if (ie and ie.value is not None) else 0.0
        fact_ids["ebit_total_profit"] = tp.fact_id
        fact_ids["ebit_interest_expense"] = ie.fact_id if (ie and ie.value is not None) else None
        notes.append("EBIT_FROM_TOTAL_PROFIT_PLUS_INTEREST")
        if ie is None or ie.value is None:
            notes.append("EBIT_INTEREST_EXPENSE_MISSING_ZEROED")
        return tp.value + ie_value

    return None


def _compute_one_year(
    year: int,
    market: str,
    cache: dict[str, dict[int, FactValue]],
) -> RoceComponents:
    """从预拉缓存计算单年 ROCE。所有数据问题降级到 notes，不抛异常。"""
    components = RoceComponents(year=year, period_end=None, market=market)

    # 取 period_end（用 net_ppe 的，作为代表）
    ppe_fv = cache.get("net_ppe", {}).get(year)
    if ppe_fv:
        components.period_end = ppe_fv.period_end

    # ===== 分子 EBIT =====
    ebit = _resolve_ebit(year, market, cache, components.source_fact_ids, components.notes)
    if ebit is None:
        components.notes.append("EBIT_NOT_AVAILABLE")
        return components
    components.ebit = ebit

    # ===== 分母 =====
    ca = cache.get("current_assets", {}).get(year)
    cl = cache.get("current_liabilities", {}).get(year)
    cash = cache.get("cash", {}).get(year)
    sti = cache.get("short_term_investments", {}).get(year)
    std = cache.get("short_term_debt", {}).get(year)
    cpltd = cache.get("current_portion_long_term_debt", {}).get(year)
    cll = cache.get("current_lease_liability", {}).get(year)

    if ca is None or ca.value is None:
        components.notes.append("CURRENT_ASSETS_MISSING")
        return components
    if cl is None or cl.value is None:
        components.notes.append("CURRENT_LIAB_MISSING")
        return components
    if cash is None or cash.value is None:
        components.notes.append("CASH_MISSING")
        return components
    if ppe_fv is None or ppe_fv.value is None:
        components.notes.append("PPE_MISSING")
        return components

    components.source_fact_ids["current_assets"] = ca.fact_id
    components.source_fact_ids["current_liabilities"] = cl.fact_id
    components.source_fact_ids["cash"] = cash.fact_id
    components.source_fact_ids["net_ppe"] = ppe_fv.fact_id

    # short_term_investments：缺失置 0 + 标低置信
    if sti is None or sti.value is None:
        sti_value = 0.0
        components.notes.append("EXCESS_CASH_PROXY_LOW_CONFIDENCE")
        components.source_fact_ids["short_term_investments"] = None
    else:
        sti_value = sti.value
        components.source_fact_ids["short_term_investments"] = sti.fact_id

    # 流动负债扣减项缺失一律置 0（PRD 允许）
    std_value = std.value if (std and std.value is not None) else 0.0
    cpltd_value = cpltd.value if (cpltd and cpltd.value is not None) else 0.0
    cll_value = cll.value if (cll and cll.value is not None) else 0.0
    components.source_fact_ids["short_term_debt"] = std.fact_id if (std and std.value is not None) else None
    components.source_fact_ids["current_portion_long_term_debt"] = (
        cpltd.fact_id if (cpltd and cpltd.value is not None) else None
    )
    components.source_fact_ids["current_lease_liability"] = (
        cll.fact_id if (cll and cll.value is not None) else None
    )

    operating_ca = ca.value - cash.value - sti_value
    operating_cl = cl.value - std_value - cpltd_value - cll_value
    nwc = operating_ca - operating_cl
    capital_employed = nwc + ppe_fv.value

    components.operating_current_assets = operating_ca
    components.operating_current_liabilities = operating_cl
    components.nwc_ex_cash = nwc
    components.net_ppe = ppe_fv.value
    components.capital_employed = capital_employed

    # ===== ROCE =====
    if capital_employed <= 0:
        components.notes.append("NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED")
        # 不自动排除，但 ROCE 不可比，置 None
        return components

    components.roce = ebit / capital_employed
    return components


def compute_roce_series(
    db: Session,
    company_id: str,
    year_range: tuple[int, int],
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
) -> list[RoceComponents]:
    """批量计算多年 ROCE。预拉所有字段后逐年组装，减少 DB 往返。"""
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []
    if fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    numerator_fields = _NUMERATOR_FIELDS_US if market == "US" else _NUMERATOR_FIELDS_CN
    canonicals = numerator_fields + _DENOMINATOR_FIELDS
    cache = _bulk_fetch(db, company_id, canonicals, year_range, market, fiscal_year_end_month)

    out: list[RoceComponents] = []
    for year in range(year_range[0], year_range[1] + 1):
        out.append(_compute_one_year(year, market, cache))
    return out


def compute_roce_year(
    db: Session,
    company_id: str,
    year: int,
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
) -> RoceComponents:
    """单年 ROCE 便捷入口。"""
    series = compute_roce_series(
        db,
        company_id,
        (year, year),
        market=market,
        fiscal_year_end_month=fiscal_year_end_month,
    )
    return series[0] if series else RoceComponents(year=year, period_end=None, market=market or "UNKNOWN")


def evaluate_quality_gate(
    series: list[RoceComponents],
    *,
    threshold: float = 0.20,
    count_5y_required: int = 4,
    count_10y_required: int = 8,
) -> QualityGate:
    """对 ROCE 时间序列执行 5Y/10Y 质量门槛判定（PRD 第 4 节工程化判定）。

    窗口取「最近 N 个完整财年」而非「最近 N 个有效 ROCE 年」。
    若窗口内多数年份 NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED → 不通过门槛（fail_reason=Q5_RECENT_NEG_CAP）。

    series 须按年份升序（compute_roce_series 已保证）。
    """
    # 最近 5/10 个财年窗口（含 invalid）
    recent_5y = [c for c in series if c.period_end is not None][-5:]
    recent_10y = [c for c in series if c.period_end is not None][-10:]
    valid_5y = [c for c in recent_5y if c.is_valid]
    valid_10y = [c for c in recent_10y if c.is_valid]

    n_valid_5y = len(valid_5y)
    n_valid_10y = len(valid_10y)
    n_recent_5y = len(recent_5y)

    median_5y = statistics.median([c.roce for c in valid_5y]) if valid_5y else None
    median_10y = statistics.median([c.roce for c in valid_10y]) if valid_10y else None
    count_ge_5y = sum(1 for c in valid_5y if c.roce >= threshold)

    fail_reason: Optional[str] = None
    pass_5y = False

    if n_recent_5y < 5:
        fail_reason = "Q1_INSUFFICIENT_HISTORY"
    elif n_recent_5y - n_valid_5y >= 2:
        # 近 5 年内 ≥ 2 年 NEGATIVE_CAP_EMP 或字段缺失 → 走人工覆核
        fail_reason = "Q5_RECENT_NEG_CAP_OR_MISSING"
    else:
        median_ok = median_5y is not None and median_5y >= threshold
        count_ok = count_ge_5y >= count_5y_required
        pass_5y = median_ok and count_ok
        if not pass_5y:
            fail_reason = "Q3_FAIL_MEDIAN" if not median_ok else "Q3_FAIL_COUNT"

    # 10Y 强通过：近 10 个财年中 ≥ count_10y_required 年有效，且 valid 中位数 ≥ threshold
    strong = (n_valid_10y >= count_10y_required) and (median_10y is not None and median_10y >= threshold)

    return QualityGate(
        n_valid_years=n_valid_5y,
        n_valid_10y=n_valid_10y,
        median_5y=median_5y,
        median_10y=median_10y,
        count_ge_threshold_5y=count_ge_5y,
        pass_5y_gate=pass_5y,
        strong_track_record=strong,
        fail_reason=fail_reason,
    )
