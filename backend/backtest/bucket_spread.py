# -*- coding: utf-8 -*-
"""Bucket Spread 回测（PRD 第 8 节核心验证）。

输入：一次已完成的 screen_run。
对每家公司：
- 起始价：max(trade_date ≤ run.as_of_date) 的 close
- 终止价：max(trade_date ≤ forward_end) 的 close
- forward_return = (end / start) - 1

按 5 状态分桶统计 mean / median / win_rate / count。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.market_bar import MarketBar
from backend.models.screen_result import ScreenResult
from backend.models.screen_run import ScreenRun
from backend.models.security import Security

from backend.backtest.metrics_eval import (
    annualize_return,
    quantile,
    safe_mean,
    safe_median,
    win_rate,
)


# 5 状态固定顺序，便于前端展示
BUCKETS = ("HighConviction", "NearFairPrice", "TooExpensive", "Review", "Rejected")


@dataclass
class BucketStats:
    status: str
    n: int = 0
    mean_return: float = float("nan")
    median_return: float = float("nan")
    p25_return: float = float("nan")
    p75_return: float = float("nan")
    win_rate: float = float("nan")
    mean_cagr: float = float("nan")
    # 每只股票详情（供前端展开）
    samples: list[dict] = field(default_factory=list)


@dataclass
class BucketSpreadReport:
    run_id: int
    as_of_date: date
    forward_end: date
    forward_years: float
    universe_size: int
    buckets: dict[str, BucketStats]


def _latest_close_on_or_before(
    db: Session,
    security_id: str,
    asof: date,
    *,
    lookback_days: int = 60,
) -> Optional[float]:
    """取 ≤ asof 的最新 close。lookback_days 防止节假日空档过大。"""
    from datetime import timedelta
    earliest = asof - timedelta(days=lookback_days)
    row = db.execute(
        select(MarketBar.close)
        .where(
            and_(
                MarketBar.security_id == security_id,
                MarketBar.trade_date <= asof,
                MarketBar.trade_date >= earliest,
                MarketBar.close.isnot(None),
                MarketBar.close > 0,
            )
        )
        .order_by(MarketBar.trade_date.desc())
        .limit(1)
    ).first()
    return float(row.close) if row else None


def _security_id_for(db: Session, company_id: str) -> Optional[str]:
    """取该公司任意 security（多 security 公司按 security_id 排序取首个）。"""
    return db.scalar(
        select(Security.security_id)
        .where(Security.company_id == company_id)
        .order_by(Security.security_id)
        .limit(1)
    )


def run_bucket_spread(
    run_id: int,
    forward_end: date,
    *,
    sample_limit_per_bucket: int = 30,
) -> BucketSpreadReport:
    """主入口。"""
    db = SessionLocal()
    try:
        run = db.get(ScreenRun, run_id)
        if run is None:
            raise ValueError(f"screen_run {run_id} not found")
        if forward_end <= run.as_of_date:
            raise ValueError("forward_end 必须晚于 run.as_of_date")

        forward_days = (forward_end - run.as_of_date).days
        forward_years = forward_days / 365.25

        # 取该 run 的所有 screen_result + company + security
        rows = db.execute(
            select(ScreenResult, Company)
            .join(Company, ScreenResult.company_id == Company.company_id)
            .where(ScreenResult.run_id == run_id)
        ).all()

        bucket_returns: dict[str, list[tuple[str, float, float, float]]] = {b: [] for b in BUCKETS}
        # 每个 sample: (ticker, start_price, end_price, return_pct)

        for sr, company in rows:
            if sr.status not in BUCKETS:
                continue
            sec_id = _security_id_for(db, company.company_id)
            if sec_id is None:
                continue
            start_close = _latest_close_on_or_before(db, sec_id, run.as_of_date)
            end_close = _latest_close_on_or_before(db, sec_id, forward_end)
            if start_close is None or end_close is None:
                continue
            ret = end_close / start_close - 1.0
            ticker = db.scalar(select(Security.ticker).where(Security.security_id == sec_id)) or company.company_id
            bucket_returns[sr.status].append((ticker, start_close, end_close, ret))

        buckets_out: dict[str, BucketStats] = {}
        for b in BUCKETS:
            samples = bucket_returns[b]
            returns = [s[3] for s in samples]
            stats = BucketStats(
                status=b,
                n=len(samples),
                mean_return=safe_mean(returns),
                median_return=safe_median(returns),
                p25_return=quantile(returns, 0.25),
                p75_return=quantile(returns, 0.75),
                win_rate=win_rate(returns),
                mean_cagr=annualize_return(safe_mean(returns), forward_years),
            )
            # 详情按 return 排序，取头尾共 sample_limit
            sorted_samples = sorted(samples, key=lambda s: s[3], reverse=True)
            head = sorted_samples[: sample_limit_per_bucket // 2]
            tail = sorted_samples[-(sample_limit_per_bucket // 2):] if len(sorted_samples) > sample_limit_per_bucket else []
            for tk, sp, ep, r in head:
                stats.samples.append({
                    "ticker": tk, "start": sp, "end": ep, "return_pct": r, "kind": "top",
                })
            for tk, sp, ep, r in tail:
                if (tk, sp, ep, r) in head:
                    continue
                stats.samples.append({
                    "ticker": tk, "start": sp, "end": ep, "return_pct": r, "kind": "bottom",
                })
            buckets_out[b] = stats

        return BucketSpreadReport(
            run_id=run_id,
            as_of_date=run.as_of_date,
            forward_end=forward_end,
            forward_years=forward_years,
            universe_size=len(rows),
            buckets=buckets_out,
        )
    finally:
        db.close()


def report_to_dict(report: BucketSpreadReport) -> dict:
    return {
        "run_id": report.run_id,
        "as_of_date": report.as_of_date.isoformat(),
        "forward_end": report.forward_end.isoformat(),
        "forward_years": round(report.forward_years, 2),
        "universe_size": report.universe_size,
        "buckets": {
            b: {
                "status": s.status,
                "n": s.n,
                "mean_return": s.mean_return,
                "median_return": s.median_return,
                "p25_return": s.p25_return,
                "p75_return": s.p75_return,
                "win_rate": s.win_rate,
                "mean_cagr": s.mean_cagr,
                "samples": s.samples,
            }
            for b, s in report.buckets.items()
        },
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Darwen Bucket Spread 回测")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--forward-end", default="2026-05-08")
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()

    forward_end = date.fromisoformat(args.forward_end)
    report = run_bucket_spread(args.run_id, forward_end, sample_limit_per_bucket=args.sample_limit)
    out = report_to_dict(report)
    # 概览不打 samples 太长
    summary = {k: v for k, v in out.items() if k != "buckets"}
    summary["buckets"] = {
        b: {k: v for k, v in s.items() if k != "samples"}
        for b, s in out["buckets"].items()
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
