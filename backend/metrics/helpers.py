# -*- coding: utf-8 -*-
"""Fact 表单点查询与序列查询。

抽象层职责：
1. canonical 名 → concept 候选列表（field_map 提供）
2. company.market → source_type 优先级链
3. concept 候选回退查询，返回首个命中
4. 同时返回 fact_id 供血缘日志（metric_lineage_log）

所有函数均为只读，不写库。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import case

from backend.models.company import Company
from backend.models.fact import Fact

from backend.metrics.field_map import candidate_concepts, source_chain


@dataclass(frozen=True)
class FactValue:
    """单条 fact 查询结果。

    value 为 None 表示未命中；fact_id 仅在命中时有值。
    source_type / source_concept 记录命中的数据源与原始字段名，供血缘追溯。
    """
    value: Optional[float]
    fact_id: Optional[str] = None
    source_type: Optional[str] = None
    source_concept: Optional[str] = None
    period_end: Optional[date] = None

    @property
    def is_hit(self) -> bool:
        return self.value is not None and self.fact_id is not None


def _get_market(db: Session, company_id: str) -> Optional[str]:
    """读 company.market（US|CN_A）。"""
    return db.scalar(select(Company.market).where(Company.company_id == company_id))


def get_fact_value(
    db: Session,
    company_id: str,
    canonical: str,
    period_end: date,
    *,
    market: Optional[str] = None,
) -> FactValue:
    """精确按 (company, canonical, period_end) 取值，concept 候选 + source 链回退。

    market 可显式传入避免重复查 company 表（批量调用场景）。
    """
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return FactValue(value=None)

    for src in source_chain(market):
        for concept in candidate_concepts(canonical, src):
            row = db.execute(
                select(Fact.fact_id, Fact.value)
                .where(
                    and_(
                        Fact.company_id == company_id,
                        Fact.source_type == src,
                        Fact.concept == concept,
                        Fact.period_end == period_end,
                    )
                )
                .order_by(case((Fact.accepted_date.is_(None), 1), else_=0), Fact.accepted_date.desc())
                .limit(1)
            ).first()
            if row is not None and row.value is not None:
                return FactValue(
                    value=float(row.value),
                    fact_id=row.fact_id,
                    source_type=src,
                    source_concept=concept,
                    period_end=period_end,
                )
    return FactValue(value=None)


def get_fact_value_asof(
    db: Session,
    company_id: str,
    canonical: str,
    asof_date: date,
    *,
    market: Optional[str] = None,
    annual_only: bool = False,
    fiscal_year_end_month: Optional[int] = None,
    disclosure_lag_days: int = 120,
) -> FactValue:
    """取 ≤ asof_date 的最新可见 fact。

    可见性三轨过滤（按优先级）：
    1. accepted_date <= asof（严格点时，SEC / TS-FS 有此字段）
    2. accepted_date NULL 且 available_date <= asof（部分数据集）
    3. accepted_date 和 available_date 双 NULL（AKSHARE）→ 用 period_end + disclosure_lag_days
       作为隐含可见期（A 股年报披露窗口约 4 个月）

    annual_only=True：仅取月份匹配 fiscal_year_end_month 的 fact（避免季报混入）。
    """
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return FactValue(value=None)

    if annual_only and fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    from sqlalchemy import func as sa_func
    from datetime import timedelta

    lag_cutoff = asof_date - timedelta(days=disclosure_lag_days)

    for src in source_chain(market):
        for concept in candidate_concepts(canonical, src):
            conditions = [
                Fact.company_id == company_id,
                Fact.source_type == src,
                Fact.concept == concept,
                Fact.value.isnot(None),
                # 三轨可见性过滤
                (
                    (Fact.accepted_date.isnot(None)) & (Fact.accepted_date <= asof_date)
                ) | (
                    (Fact.accepted_date.is_(None)) & (Fact.available_date.isnot(None)) &
                    (Fact.available_date <= asof_date)
                ) | (
                    (Fact.accepted_date.is_(None)) & (Fact.available_date.is_(None)) &
                    (Fact.period_end <= lag_cutoff)
                ),
            ]
            if annual_only and fiscal_year_end_month:
                conditions.append(sa_func.month(Fact.period_end) == fiscal_year_end_month)

            row = db.execute(
                select(Fact.fact_id, Fact.value, Fact.period_end)
                .where(and_(*conditions))
                .order_by(Fact.period_end.desc())
                .limit(1)
            ).first()
            if row is not None:
                return FactValue(
                    value=float(row.value),
                    fact_id=row.fact_id,
                    source_type=src,
                    source_concept=concept,
                    period_end=row.period_end,
                )
    return FactValue(value=None)


def get_fact_series_asof(
    db: Session,
    company_id: str,
    canonical: str,
    asof_date: date,
    *,
    market: Optional[str] = None,
    disclosure_lag_days: int = 120,
) -> list[FactValue]:
    """取 ≤ asof_date 点时可见的逐期 fact 序列（含季报），按 period_end 降序、每期一条。

    复用 get_fact_value_asof 的三轨可见性；取首个有数据的 source/concept 的完整序列，
    同一 period_end 多条时保留 accepted_date 最新一条。用于 TTM 等需逐季序列的口径。
    """
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []

    from sqlalchemy import func as sa_func  # noqa: F401  (与其它函数保持一致的局部导入风格)
    from datetime import timedelta

    lag_cutoff = asof_date - timedelta(days=disclosure_lag_days)
    visibility = (
        (Fact.accepted_date.isnot(None)) & (Fact.accepted_date <= asof_date)
    ) | (
        (Fact.accepted_date.is_(None)) & (Fact.available_date.isnot(None)) &
        (Fact.available_date <= asof_date)
    ) | (
        (Fact.accepted_date.is_(None)) & (Fact.available_date.is_(None)) &
        (Fact.period_end <= lag_cutoff)
    )

    for src in source_chain(market):
        for concept in candidate_concepts(canonical, src):
            rows = db.execute(
                select(Fact.fact_id, Fact.value, Fact.period_end)
                .where(
                    and_(
                        Fact.company_id == company_id,
                        Fact.source_type == src,
                        Fact.concept == concept,
                        Fact.value.isnot(None),
                        visibility,
                    )
                )
                .order_by(
                    Fact.period_end.desc(),
                    case((Fact.accepted_date.is_(None), 1), else_=0),
                    Fact.accepted_date.desc(),
                )
            ).all()
            if rows:
                seen: set[date] = set()
                out: list[FactValue] = []
                for r in rows:
                    if r.period_end in seen:
                        continue
                    seen.add(r.period_end)
                    out.append(
                        FactValue(
                            value=float(r.value),
                            fact_id=r.fact_id,
                            source_type=src,
                            source_concept=concept,
                            period_end=r.period_end,
                        )
                    )
                return out
    return []


def get_annual_periods(
    db: Session,
    company_id: str,
    canonical: str,
    year_range: tuple[int, int],
    *,
    market: Optional[str] = None,
    fiscal_year_end_month: Optional[int] = None,
    annual_only: bool = True,
) -> list[FactValue]:
    """按年返回 fact 值序列，每年最多一条。

    year_range = (start_year, end_year)，闭区间。
    annual_only=True（默认）：仅接受 period_end.month == fiscal_year_end_month 的 fact，
        即严格年报数据，避免取到季报。fiscal_year_end_month 未传则自动推断。
    annual_only=False：取该年 period_end 最大值（不论月份），用于稀缺字段兜底。

    跨 source 回退：单年内若高优先 source（如 TS-FS）无年报数据，自动回退到下一 source（如 AKSHARE）。
    返回按 period_end 升序排列，仅包含命中年份。
    """
    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return []

    if annual_only and fiscal_year_end_month is None:
        fiscal_year_end_month = get_fiscal_year_end(db, company_id, market=market)

    start_year, end_year = year_range
    by_year: dict[int, FactValue] = {}

    for year in range(start_year, end_year + 1):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        for src in source_chain(market):
            if year in by_year:
                break
            for concept in candidate_concepts(canonical, src):
                conditions = [
                    Fact.company_id == company_id,
                    Fact.source_type == src,
                    Fact.concept == concept,
                    Fact.period_end >= year_start,
                    Fact.period_end <= year_end,
                    Fact.value.isnot(None),
                ]
                if annual_only and fiscal_year_end_month:
                    # MySQL MONTH() 提取月份
                    from sqlalchemy import func as sa_func
                    conditions.append(sa_func.month(Fact.period_end) == fiscal_year_end_month)

                row = db.execute(
                    select(Fact.fact_id, Fact.value, Fact.period_end)
                    .where(and_(*conditions))
                    .order_by(
                        Fact.period_end.desc(),
                        case((Fact.accepted_date.is_(None), 1), else_=0),
                        Fact.accepted_date.desc(),
                    )
                    .limit(1)
                ).first()
                if row is not None:
                    by_year[year] = FactValue(
                        value=float(row.value),
                        fact_id=row.fact_id,
                        source_type=src,
                        source_concept=concept,
                        period_end=row.period_end,
                    )
                    break  # 跳出 concept 候选
            # 当前 source 处理完，若已命中该年则不必走 fallback source

    return [by_year[y] for y in sorted(by_year)]


def get_fiscal_year_end(
    db: Session,
    company_id: str,
    *,
    market: Optional[str] = None,
) -> Optional[int]:
    """返回公司财年末月份（1-12）。

    优先策略：
    1. company.fiscal_year_end_month（权威，由 SEC submissions.fiscalYearEnd 填充；A 股 12）
    2. 启发式 NetIncomeLoss 每年最大值 period_end 月份众数
    3. 启发式 Revenues 月份众数

    启发式对 TSLA / NVDA 等公司失败（NI 数据噪声导致月份判定错），
    所以权威字段优先。
    """
    # 1. 优先从 DB 读权威值
    fye = db.scalar(
        select(Company.fiscal_year_end_month).where(Company.company_id == company_id)
    )
    if fye is not None:
        return int(fye)

    if market is None:
        market = _get_market(db, company_id)
        if market is None:
            return None

    if market == "CN_A":
        return 12

    # 美股优先用 NetIncomeLoss 取每年最大值的月份
    for src in source_chain(market):
        for concept in candidate_concepts("net_income", src):
            # 取每年最大 NI 值的 period_end，然后看月份众数
            sub = (
                select(Fact.period_end, Fact.value)
                .where(
                    and_(
                        Fact.company_id == company_id,
                        Fact.source_type == src,
                        Fact.concept == concept,
                        Fact.value.isnot(None),
                    )
                )
            )
            rows = db.execute(sub).all()
            if not rows:
                continue
            # 按年分组，取每年值最大的 period_end
            by_year: dict[int, tuple[date, float]] = {}
            for pe, val in rows:
                year = pe.year
                if year not in by_year or val > by_year[year][1]:
                    by_year[year] = (pe, val)
            month_counts: dict[int, int] = {}
            for pe, _ in by_year.values():
                month_counts[pe.month] = month_counts.get(pe.month, 0) + 1
            if month_counts:
                return max(month_counts.items(), key=lambda kv: kv[1])[0]

    # 回退：Revenue period_end 月份众数（不可靠但聊胜于无）
    for src in source_chain(market):
        for concept in candidate_concepts("revenue", src):
            rows = db.execute(
                select(Fact.period_end)
                .where(
                    and_(
                        Fact.company_id == company_id,
                        Fact.source_type == src,
                        Fact.concept == concept,
                    )
                )
                .order_by(Fact.period_end.desc())
                .limit(20)
            ).scalars().all()
            if not rows:
                continue
            month_counts: dict[int, int] = {}
            for d in rows:
                month_counts[d.month] = month_counts.get(d.month, 0) + 1
            return max(month_counts.items(), key=lambda kv: kv[1])[0]
    return None
