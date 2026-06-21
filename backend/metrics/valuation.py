# -*- coding: utf-8 -*-
"""估值指标（PRD V 层依赖）。

输出（截面，as_of_date 一行）：
- pe_ttm = market_cap / net_income_ttm
  （net_income_ttm 为真 4 季 TTM，YTD 差分法：最近完整财年 + 本年最新YTD − 去年同期YTD；
   缺季报数据时降级回最近年报净利润，标 PE_TTM_ANNUAL_PROXY。见 _net_income_ttm）
- ev_ebit = (market_cap + total_debt - cash - short_term_investments) / EBIT_latest
  （备用估值，与 PE 互补；轻资产服务业 PE 失真时参考）
- market_cap = close × shares_outstanding（皆取 ≤ as_of_date 最新）

PRD V 层触发（V 层判定，本模块只输出原值）：
- V1: EPS ≤ 0 → 不进入买入状态
- V2 strict: PE_TTM ≤ 14.9 → 可买入候选
- V3 standard: 14.9-22（视等级）

降级标签：
- NO_MARKET_PRICE              market_bar 无 as_of_date 前数据
- NO_SHARES_OUTSTANDING        shares_outstanding 字段缺
- NEGATIVE_NET_INCOME          净利润 ≤ 0，pe_ttm 无意义置 None
- PE_TTM_ANNUAL_PROXY          TTM 季报数据不足，降级用最近年报净利润
- EBIT_MISSING                 EBIT 缺
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.market_bar import MarketBar
from backend.models.security import Security

from backend.metrics.helpers import (
    FactValue,
    _get_market,
    get_fact_value_asof,
    get_fact_series_asof,
    get_fiscal_year_end,
    get_annual_periods,
)


FORMULA_VERSION = "valuation_v1"


@dataclass
class ValuationSnapshot:
    """单股截面估值快照。"""
    company_id: str
    as_of_date: date
    market: str

    latest_close: Optional[float] = None
    latest_trade_date: Optional[date] = None
    shares_outstanding: Optional[float] = None
    shares_period_end: Optional[date] = None
    market_cap: Optional[float] = None

    net_income_ttm: Optional[float] = None
    pe_ttm: Optional[float] = None

    ebit: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_sti: Optional[float] = None
    enterprise_value: Optional[float] = None
    ev_ebit: Optional[float] = None

    notes: list[str] = field(default_factory=list)
    source_fact_ids: dict[str, Optional[str]] = field(default_factory=dict)


def _pick_common_security(db: Session, company_id: str) -> Optional[str]:
    """挑选公司的普通股 security_id。

    选优先级：
    1. ticker 不含 '-' 且不含 '.PR'（排除优先股 JPM-PK / BRK.A 等）
    2. 优先长度短的 ticker（普通股一般 1-5 字符，优先股带后缀更长）
    3. 兜底按 security_id 排序首个
    """
    rows = db.execute(
        select(Security.security_id, Security.ticker)
        .where(Security.company_id == company_id)
        .order_by(Security.security_id)
    ).all()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0][0]
    # 排除带 '-' 的 ticker（优先股，常见 JPM-PK / WFC-PD 等）
    common = [r for r in rows if r[1] and "-" not in r[1] and ".PR" not in (r[1] or "")]
    if common:
        # 优先 ticker 短的（普通股一般最短）
        common.sort(key=lambda r: (len(r[1] or ""), r[1] or ""))
        return common[0][0]
    return rows[0][0]


def _get_latest_close(
    db: Session,
    company_id: str,
    asof_date: date,
) -> tuple[Optional[float], Optional[date], Optional[float]]:
    """取该公司普通股 security 在 ≤ asof_date 的最新 close 与权威 market_cap。

    返回 (close, trade_date, market_cap_from_data_source)。
    market_cap：A 股从 Tushare daily_basic 落库到 market_bar.market_cap（元单位），
    若有则视为权威值；美股 market_bar 多数 NULL，留给 valuation 自算。

    多 security 公司（如金融股有大量优先股）：优先取 ticker 无 '-' 的普通股。
    """
    sec_id = _pick_common_security(db, company_id)
    if sec_id is None:
        return None, None, None
    row = db.execute(
        select(MarketBar.close, MarketBar.trade_date, MarketBar.market_cap)
        .where(MarketBar.security_id == sec_id)
        .where(MarketBar.trade_date <= asof_date)
        .where(MarketBar.close.isnot(None))
        .order_by(MarketBar.trade_date.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None, None
    mc = float(row.market_cap) if row.market_cap is not None else None
    return float(row.close), row.trade_date, mc


def _net_income_ttm(
    db: Session,
    company_id: str,
    asof_date: date,
    market: str,
    fy_end_month: int,
) -> tuple[Optional[float], Optional[str], list[str]]:
    """真 TTM 净利润（YTD 差分法）。返回 (value, 主血缘 fact_id, notes)。

    fact 表 net_income 多为 YTD 累计值（年初至今），故：
    - 最新一期即年报（period_end 月 == 财年末月）→ 直接用其全年值；
    - 否则为季报 YTD → TTM = 最近完整财年 + 本年最新 YTD − 去年同期 YTD；
    - 关键项缺失 → 降级回最近完整财年（notes 加 PE_TTM_ANNUAL_PROXY）。
    """
    series = get_fact_series_asof(db, company_id, "net_income", asof_date, market=market)
    if not series:
        return None, None, ["NET_INCOME_MISSING"]
    cur = series[0]  # period_end 最大（最新一期）
    if cur.period_end.month == fy_end_month:
        return cur.value, cur.fact_id, []  # 最新就是年报，即全年值
    # 季报 YTD：TTM = 最近完整财年 + 本年最新 YTD − 去年同期 YTD
    cur_year = cur.period_end.year
    fy_last = next(
        (f for f in series
         if f.period_end.month == fy_end_month and f.period_end < date(cur_year, 1, 1)),
        None,
    )
    ytd_prior = next(
        (f for f in series
         if f.period_end.month == cur.period_end.month and f.period_end.year == cur_year - 1),
        None,
    )
    if fy_last is not None and ytd_prior is not None:
        return fy_last.value + cur.value - ytd_prior.value, cur.fact_id, []
    if fy_last is not None:  # 降级：回退最近完整财年
        return fy_last.value, fy_last.fact_id, ["PE_TTM_ANNUAL_PROXY"]
    return None, None, ["NET_INCOME_MISSING"]


def compute_valuation_snapshot(
    db: Session,
    company_id: str,
    asof_date: date,
    *,
    market: Optional[str] = None,
) -> ValuationSnapshot:
    """计算截面估值。"""
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return ValuationSnapshot(company_id=company_id, as_of_date=asof_date, market="UNKNOWN")

    snap = ValuationSnapshot(company_id=company_id, as_of_date=asof_date, market=market)
    fy_end_month = get_fiscal_year_end(db, company_id, market=market)

    # 1. 最新 close（+ 数据源权威 market_cap，A 股 Tushare daily_basic 已落库）
    close, trade_date, mc_from_source = _get_latest_close(db, company_id, asof_date)
    if close is None:
        snap.notes.append("NO_MARKET_PRICE")
    else:
        snap.latest_close = close
        snap.latest_trade_date = trade_date

    # 2. 最新 shares_outstanding（shares 是截面字段，取 ≤ asof 最新即可。
    # 不限 annual_only，因 dei.EntityCommonStockSharesOutstanding 是季度更新，
    # 且 SEC us-gaap.WeightedAverage* 单位不规范（部分公司报百万股而非股）。
    sh_fv = get_fact_value_asof(
        db, company_id, "shares_outstanding", asof_date, market=market,
    )
    if not sh_fv.is_hit:
        snap.notes.append("NO_SHARES_OUTSTANDING")
    else:
        snap.shares_outstanding = sh_fv.value
        snap.shares_period_end = sh_fv.period_end
        snap.source_fact_ids["shares_outstanding"] = sh_fv.fact_id

    # 3. market_cap：优先用数据源权威值（Tushare total_mv 已写到 market_bar.market_cap），
    # 回退到 close × shares_outstanding 自算
    if mc_from_source is not None and mc_from_source > 0:
        snap.market_cap = mc_from_source
        snap.notes.append("MC_FROM_DATA_SOURCE")
    elif snap.latest_close is not None and snap.shares_outstanding is not None:
        snap.market_cap = snap.latest_close * snap.shares_outstanding

    # 4. net_income TTM（真 4 季 TTM，YTD 差分法；缺失降级回最近年报）
    ttm_val, ttm_fact_id, ttm_notes = _net_income_ttm(
        db, company_id, asof_date, market, fy_end_month,
    )
    snap.notes.extend(ttm_notes)
    if ttm_val is None:
        if "NET_INCOME_MISSING" not in snap.notes:
            snap.notes.append("NET_INCOME_MISSING")
    else:
        snap.net_income_ttm = ttm_val
        if ttm_fact_id:
            snap.source_fact_ids["net_income"] = ttm_fact_id
        if ttm_val <= 0:
            snap.notes.append("NEGATIVE_NET_INCOME")

    # 5. pe_ttm
    if (
        snap.market_cap is not None
        and snap.market_cap > 0
        and snap.net_income_ttm is not None
        and snap.net_income_ttm > 0
    ):
        snap.pe_ttm = snap.market_cap / snap.net_income_ttm

    # 6. EBIT 取最近年报
    ebit_fv = get_fact_value_asof(
        db, company_id, "operating_income", asof_date,
        market=market, annual_only=True, fiscal_year_end_month=fy_end_month,
    )
    if ebit_fv.is_hit:
        snap.ebit = ebit_fv.value
        snap.source_fact_ids["operating_income"] = ebit_fv.fact_id
    else:
        snap.notes.append("EBIT_MISSING")

    # 7. EV = market_cap + total_debt - cash - STI（取最近年报口径）
    debt = 0.0
    debt_components_hit = 0
    for canonical in ("short_term_debt", "current_portion_long_term_debt", "long_term_debt"):
        fv = get_fact_value_asof(
            db, company_id, canonical, asof_date,
            market=market, annual_only=True, fiscal_year_end_month=fy_end_month,
        )
        if fv.is_hit:
            debt += fv.value
            debt_components_hit += 1
            snap.source_fact_ids[canonical] = fv.fact_id
    cash_total = 0.0
    cash_hit = False
    for canonical in ("cash", "short_term_investments"):
        fv = get_fact_value_asof(
            db, company_id, canonical, asof_date,
            market=market, annual_only=True, fiscal_year_end_month=fy_end_month,
        )
        if fv.is_hit:
            cash_total += fv.value
            cash_hit = True
            snap.source_fact_ids[canonical] = fv.fact_id

    if debt_components_hit > 0 or cash_hit:
        snap.total_debt = debt
        snap.cash_and_sti = cash_total

    if snap.market_cap is not None and snap.total_debt is not None and snap.cash_and_sti is not None:
        snap.enterprise_value = snap.market_cap + snap.total_debt - snap.cash_and_sti
        if snap.ebit is not None and snap.ebit > 0:
            snap.ev_ebit = snap.enterprise_value / snap.ebit

    return snap
