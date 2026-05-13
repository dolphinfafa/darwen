# -*- coding: utf-8 -*-
"""E6 点时偏差校验（PRD 第 8 节实验）。

两个核心校验：

1. **Lookback 敏感性**：以多个 lookback_days 跑同一段月度回测，看 CAGR
   是否随 lookback 收紧而下降。若下降明显，说明短 lookback 引入了未来数据；
   若几乎不变，说明回测已点时严格。

2. **Fact accepted_date 可见性审计**：对一组历史 rebalance dates，统计
   metric_periodic 用到的 fact 的 (accepted_date, period_end) 与 rebalance
   的关系。量化"PRD 期望披露 lag 内已可见"的覆盖率。

PRD 第 8 节 E6：filing/ann_date 回放 vs 静态年报应得到相近结果（差异 < 5%
则视为点时严格）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.fact import Fact
from backend.backtest.v2_engine import monthly_rebalance


log = logging.getLogger(__name__)


@dataclass
class LookbackResult:
    lookback_days: int
    cagr: Optional[float]
    sharpe: Optional[float]
    max_drawdown: Optional[float]
    total_return: Optional[float]
    n_candidates_avg: float
    n_months: int


@dataclass
class VisibilityStat:
    rebalance_date: date
    total_facts: int
    accepted_le_rebalance: int   # accepted_date ≤ rebalance（已披露可见）
    accepted_after_rebalance: int  # accepted_date > rebalance（点时违规：未来数据）
    accepted_null: int           # 缺 accepted_date（V1 旧数据 / AKSHARE）
    median_pub_lag_days: Optional[float]  # period_end → accepted_date 中位延迟


def lookback_sensitivity(
    *,
    market: str = "US",
    start: date = date(2020, 1, 1),
    end: date = date(2024, 12, 31),
    lookbacks: tuple[int, ...] = (0, 30, 60, 90, 120, 180),
    roce_threshold: float = 0.20,
    pe_max: float = 14.9,
) -> list[LookbackResult]:
    """对多个 lookback_days 分别跑月度回测，返回结果列表。"""
    out: list[LookbackResult] = []
    for lb in lookbacks:
        log.info("跑 lookback_days=%d ...", lb)
        rpt = monthly_rebalance(
            market=market, start=start, end=end,
            roce_threshold=roce_threshold, pe_max=pe_max,
            lookback_days=lb,
        )
        n_cand_avg = (
            sum(len(s.candidates) for s in rpt.snapshots) / max(len(rpt.snapshots), 1)
        )
        out.append(LookbackResult(
            lookback_days=lb,
            cagr=rpt.cagr,
            sharpe=rpt.sharpe,
            max_drawdown=rpt.max_drawdown,
            total_return=rpt.total_return,
            n_candidates_avg=n_cand_avg,
            n_months=len(rpt.monthly_returns),
        ))
    return out


def audit_visibility(
    rebalance_dates: list[date],
    *,
    market: str = "US",
    lookback_days: int = 120,
) -> list[VisibilityStat]:
    """对一组 rebalance dates 统计 fact 表点时可见性。

    对每个 rebalance d：
    - 取所有美股的 fact period_end ≤ d - lookback 的记录
    - 分类：accepted_date ≤ d（合规）/ accepted_date > d（未来数据，违规）/ NULL
    - 计算 period_end → accepted_date 中位 lag
    """
    db = SessionLocal()
    try:
        out: list[VisibilityStat] = []
        for d in rebalance_dates:
            cutoff = d - timedelta(days=lookback_days)
            # 限定 US source SEC 才有意义（A 股 accepted_date 多数 NULL）
            rows = db.execute(
                select(Fact.accepted_date, Fact.period_end)
                .join(Company, Fact.company_id == Company.company_id)
                .where(
                    and_(
                        Company.market == market,
                        Fact.source_type == "SEC",
                        Fact.period_end <= cutoff,
                        Fact.period_end >= d - timedelta(days=lookback_days + 365 * 3),
                    )
                )
            ).all()

            total = len(rows)
            le = 0
            after = 0
            null = 0
            lags: list[int] = []
            for ad, pe in rows:
                if ad is None:
                    null += 1
                elif ad <= d:
                    le += 1
                    if pe and ad:
                        lags.append((ad - pe).days)
                else:
                    after += 1
            import statistics
            median_lag = statistics.median(lags) if lags else None
            out.append(VisibilityStat(
                rebalance_date=d,
                total_facts=total,
                accepted_le_rebalance=le,
                accepted_after_rebalance=after,
                accepted_null=null,
                median_pub_lag_days=median_lag,
            ))
        return out
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="E6 点时偏差校验")
    parser.add_argument("--market", default="US")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--mode", choices=["lookback", "visibility", "both"], default="both")
    args = parser.parse_args()

    start_d = date.fromisoformat(args.start)
    end_d = date.fromisoformat(args.end)

    if args.mode in ("lookback", "both"):
        print("=" * 64)
        print("[1] Lookback 敏感性")
        print("=" * 64)
        results = lookback_sensitivity(
            market=args.market, start=start_d, end=end_d,
            lookbacks=(0, 30, 60, 90, 120, 180),
        )
        print(f'{"lookback":>10}  {"CAGR":>8}  {"Sharpe":>7}  {"MaxDD":>7}  {"TotalRet":>9}  {"n_cand":>7}  {"n_mo":>5}')
        for r in results:
            cagr = f'{r.cagr*100:.2f}%' if r.cagr is not None else 'n/a'
            sh = f'{r.sharpe:.2f}' if r.sharpe is not None else 'n/a'
            mdd = f'{r.max_drawdown*100:.1f}%' if r.max_drawdown is not None else 'n/a'
            tr = f'{r.total_return*100:.1f}%' if r.total_return is not None else 'n/a'
            print(f'{r.lookback_days:>10}  {cagr:>8}  {sh:>7}  {mdd:>7}  {tr:>9}  {r.n_candidates_avg:>7.1f}  {r.n_months:>5}')

    if args.mode in ("visibility", "both"):
        print("\n" + "=" * 64)
        print("[2] Fact 可见性审计（120 天 lookback）")
        print("=" * 64)
        # 每年 6 月底
        rebalance_dates = [date(y, 6, 30) for y in range(start_d.year, end_d.year + 1)]
        stats = audit_visibility(rebalance_dates, market=args.market, lookback_days=120)
        print(f'{"rebal_date":>12}  {"total":>7}  {"≤ rebal":>9}  {"> rebal":>9}  {"NULL":>6}  {"lag_p50":>8}')
        for s in stats:
            after_pct = 100 * s.accepted_after_rebalance / max(s.total_facts, 1)
            lag = f'{s.median_pub_lag_days:.0f}d' if s.median_pub_lag_days else 'n/a'
            print(f'{s.rebalance_date.isoformat():>12}  {s.total_facts:>7}  '
                  f'{s.accepted_le_rebalance:>9}  {s.accepted_after_rebalance:>9} ({after_pct:.1f}%)  '
                  f'{s.accepted_null:>6}  {lag:>8}')
