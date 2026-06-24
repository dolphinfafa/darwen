# -*- coding: utf-8 -*-
"""行业 peer 自建对标（formula_version=industry_v1）。

零外部数据，纯用 company.industry_name + fact.revenue 自建同行业基准：
- rev_cagr_3y              近 3 年营收 CAGR
- rev_growth_vs_industry   公司营收 CAGR − 同行业（同市场）中位数（显著落后 = 份额流失/掉队预警）
- industry_peer_count      同行业样本数（< 5 不计相对值，避免小样本噪声）

行业风险归类（对齐原著「不把快变化行业一刀切，看相对表现」）：相对落后做 soft 预警，
仅极端落后才 hard，多由稳健层软警告叠加升级。
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.metrics.helpers import get_annual_periods, get_fiscal_year_end, _get_market

FORMULA_VERSION = "industry_v1"
MIN_PEERS = 5   # 同行业样本 < 此数不计相对值


def _rev_cagr_3y(
    db: Session, company_id: str, market: str, fy_month: Optional[int],
    year_range: tuple[int, int], n: int = 3,
) -> tuple[Optional[float], Optional[date]]:
    series = get_annual_periods(
        db, company_id, "revenue", year_range, market=market, fiscal_year_end_month=fy_month,
    )
    vals = {fv.period_end.year: fv.value for fv in series if fv.period_end and fv.value}
    pes = {fv.period_end.year: fv.period_end for fv in series if fv.period_end}
    if not vals:
        return None, None
    last = max(vals)
    base = last - n
    if base in vals and vals[base] > 0 and vals[last] > 0:
        cagr = (vals[last] / vals[base]) ** (1.0 / n) - 1.0
        return cagr, pes.get(last)
    return None, None


def compute_industry_peer_stats(db: Session, year_range: tuple[int, int] = (2014, 2025)):
    """两遍批处理：① 各公司营收 CAGR → ② 按(市场,行业)聚合中位 → ③ 回填相对值。

    返回 (落库公司数, 有效行业组数)。落库走 _upsert_metric（延迟导入避免环依赖）。
    """
    from backend.metrics.compute import _upsert_metric

    comps = db.execute(
        select(Company.company_id, Company.market, Company.industry_name,
               Company.fiscal_year_end_month)
    ).all()

    # ① 各公司营收 CAGR
    per: dict[str, tuple[float, date, str, str]] = {}
    for cid, mkt, industry, fy in comps:
        if not mkt:
            continue
        if fy is None:
            fy = get_fiscal_year_end(db, cid, market=mkt)
        cagr, pe = _rev_cagr_3y(db, cid, mkt, fy, year_range)
        if cagr is not None and pe is not None:
            per[cid] = (cagr, pe, mkt, industry or "其他")

    # ② 按(市场,行业)聚合
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for cid, (cagr, _, mkt, industry) in per.items():
        groups[(mkt, industry)].append(cagr)
    medians = {k: statistics.median(v) for k, v in groups.items()}
    counts = {k: len(v) for k, v in groups.items()}

    # ③ 回填相对值（仅样本 ≥ MIN_PEERS）
    n_co = 0
    valid_groups = sum(1 for c in counts.values() if c >= MIN_PEERS)
    for cid, (cagr, pe, mkt, industry) in per.items():
        cnt = counts[(mkt, industry)]
        if cnt < MIN_PEERS:
            continue
        rel = cagr - medians[(mkt, industry)]
        _upsert_metric(db, cid, pe, "rev_cagr_3y", cagr, [], None, formula_version=FORMULA_VERSION)
        _upsert_metric(db, cid, pe, "rev_growth_vs_industry", rel, [], None, formula_version=FORMULA_VERSION)
        _upsert_metric(db, cid, pe, "industry_peer_count", float(cnt), [], None, formula_version=FORMULA_VERSION)
        n_co += 1
    db.commit()
    return n_co, valid_groups
