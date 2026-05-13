# -*- coding: utf-8 -*-
"""估值指标（PRD V 层依赖）。

输出（截面，as_of_date 一行）：
- pe_ttm = market_cap / net_income_annual_latest
  （v1 简化：用最近一年年报净利润作 TTM 代理；M2 末尾可升级为 4 季严格 TTM）
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


def _get_latest_close(
    db: Session,
    company_id: str,
    asof_date: date,
) -> tuple[Optional[float], Optional[date], Optional[float]]:
    """取该公司任一 security 在 ≤ asof_date 的最新 close 与权威 market_cap。

    返回 (close, trade_date, market_cap_from_data_source)。
    market_cap：A 股从 Tushare daily_basic 落库到 market_bar.market_cap（元单位），
    若有则视为权威值；美股 market_bar 多数 NULL，留给 valuation 自算。

    多 security 公司简化处理：按 security_id 排序取首个。
    """
    sec_id = db.scalar(
        select(Security.security_id)
        .where(Security.company_id == company_id)
        .order_by(Security.security_id)
        .limit(1)
    )
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

    # 2. 最新 shares_outstanding（取年报值避免季报混入；股本变化通常按年报口径）
    sh_fv = get_fact_value_asof(
        db, company_id, "shares_outstanding", asof_date,
        market=market, annual_only=True, fiscal_year_end_month=fy_end_month,
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

    # 4. net_income 取最近年报作 TTM proxy（M2.4 v1 简化，未做严格 4 季加总）
    ni_fv = get_fact_value_asof(
        db, company_id, "net_income", asof_date,
        market=market, annual_only=True, fiscal_year_end_month=fy_end_month,
    )
    if not ni_fv.is_hit:
        snap.notes.append("NET_INCOME_MISSING")
    else:
        snap.net_income_ttm = ni_fv.value
        snap.source_fact_ids["net_income"] = ni_fv.fact_id
        if ni_fv.value <= 0:
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
