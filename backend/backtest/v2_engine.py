# -*- coding: utf-8 -*-
"""月度滚动点时回测（PRD 第 8/12 节）。

每个月第一个交易日（rebalance_date）：
1. 取每家公司截至 rebalance_date 之前 N 年的 ROCE 历史（metric_periodic.roce 年序列）
   计算 5Y 中位数 + 4/5 年判定 → Q3 通过
2. 取 ≤ rebalance_date 的最新 net_debt_ebit / interest_coverage（点时严格）
3. 现算 pe_ttm：close[rebalance_date] × shares_outstanding(年报) / net_income(年报)
4. 综合裁决 5 状态
5. 持有 = HighConviction + NearFairPrice，等权
6. 持有期 = 当月

输出：
- 月度净值序列
- CAGR / Sharpe / MaxDD / WinRate
- 命中股票详情（按月）

简化点（v1）：
- R 层只跑 R1（leverage 硬规则），R4-R12 AI 全部跳过
- valuation 只算 pe_ttm（不含 ev_ebit）
- 不做行业中性化、不做 stop-loss
- 起始等权，月度再平衡

后续 v2 可扩展：基准 SPY 对比、E2 单调性、Sharpe 与 MaxDD 完整统计。
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.fact import Fact
from backend.models.market_bar import MarketBar
from backend.models.metric_periodic import MetricPeriodic
from backend.models.security import Security

from backend.backtest.metrics_eval import (
    annualize_return,
    cagr,
    quantile,
    safe_mean,
    safe_median,
    win_rate,
)


log = logging.getLogger(__name__)


# 默认窗口与阈值（M7 v1 简化）
DEFAULT_LOOKBACK_DAYS = 120  # 点时披露 lag 兜底
DEFAULT_ROCE_THRESHOLD = 0.20
DEFAULT_PE_MAX = 14.9
DEFAULT_R1_NET_DEBT_EBIT_MAX = 4.0
DEFAULT_R1_INTEREST_COVERAGE_MIN = 3.0


@dataclass
class MonthlySnapshot:
    rebalance_date: date
    candidates: list[dict] = field(default_factory=list)  # 候选股票详情
    return_pct: Optional[float] = None  # 当月组合等权回报
    nav: Optional[float] = None  # 月末净值


@dataclass
class BacktestReport:
    market: str
    start: date
    end: date
    universe_size: int
    roce_threshold: float
    pe_max: float
    nav_series: list[tuple[date, float]] = field(default_factory=list)  # [(date, nav)]
    monthly_returns: list[tuple[date, float]] = field(default_factory=list)
    snapshots: list[MonthlySnapshot] = field(default_factory=list)
    # 汇总指标
    total_return: Optional[float] = None
    cagr: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate_months: Optional[float] = None


# ---------------- 数据预拉 ----------------

def _list_us_trading_days(db: Session, start: date, end: date) -> list[date]:
    """从 market_bar 取美股交易日历（任取一只活跃股的日期序列）。"""
    rows = db.execute(
        select(MarketBar.trade_date)
        .join(Security, MarketBar.security_id == Security.security_id)
        .where(and_(Security.ticker == "AAPL", MarketBar.trade_date >= start, MarketBar.trade_date <= end))
        .order_by(MarketBar.trade_date)
    ).all()
    return [r[0] for r in rows]


def _month_starts(trading_days: list[date]) -> list[date]:
    """从交易日历提取每月第一个交易日。"""
    out: list[date] = []
    seen_keys: set[tuple[int, int]] = set()
    for d in trading_days:
        key = (d.year, d.month)
        if key not in seen_keys:
            seen_keys.add(key)
            out.append(d)
    return out


def _load_roce_history(
    db: Session, company_ids: list[str]
) -> dict[str, list[tuple[date, float]]]:
    """预拉所有公司的年度 ROCE 序列 {company_id: [(period_end, roce), ...]}"""
    rows = db.execute(
        select(MetricPeriodic.company_id, MetricPeriodic.period_end, MetricPeriodic.value)
        .where(
            and_(
                MetricPeriodic.company_id.in_(company_ids),
                MetricPeriodic.metric_name == "roce",
                MetricPeriodic.formula_version == "roce_v1",
                MetricPeriodic.value.isnot(None),
            )
        )
        .order_by(MetricPeriodic.company_id, MetricPeriodic.period_end)
    ).all()
    out: dict[str, list[tuple[date, float]]] = {}
    for cid, pe, v in rows:
        out.setdefault(cid, []).append((pe, float(v)))
    return out


def _load_leverage_history(
    db: Session, company_ids: list[str]
) -> dict[str, dict[date, dict[str, float]]]:
    """预拉杠杆指标历史 {company_id: {period_end: {net_debt_ebit, interest_coverage}}}"""
    rows = db.execute(
        select(
            MetricPeriodic.company_id, MetricPeriodic.period_end,
            MetricPeriodic.metric_name, MetricPeriodic.value,
        )
        .where(
            and_(
                MetricPeriodic.company_id.in_(company_ids),
                MetricPeriodic.metric_name.in_(["net_debt_ebit", "interest_coverage"]),
                MetricPeriodic.formula_version == "leverage_v1",
                MetricPeriodic.value.isnot(None),
            )
        )
    ).all()
    out: dict[str, dict[date, dict[str, float]]] = {}
    for cid, pe, name, v in rows:
        out.setdefault(cid, {}).setdefault(pe, {})[name] = float(v)
    return out


def _load_ni_shares(
    db: Session, company_ids: list[str], market: str,
) -> dict[str, list[tuple[date, str, float]]]:
    """预拉 fact 表中 net_income 和 shares_outstanding 年报记录。"""
    if market == "US":
        sources = ["SEC"]
        ni_concepts = ["NetIncomeLoss"]
        sh_concepts = ["CommonStockSharesOutstanding"]
    else:
        sources = ["TS-FS", "AKSHARE"]
        ni_concepts = ["net_income", "net_income_to_parent"]
        sh_concepts = ["shares_outstanding", "shares_outstanding_capital"]
    rows = db.execute(
        select(Fact.company_id, Fact.period_end, Fact.concept, Fact.value)
        .where(
            and_(
                Fact.company_id.in_(company_ids),
                Fact.source_type.in_(sources),
                Fact.concept.in_(ni_concepts + sh_concepts),
                Fact.value.isnot(None),
            )
        )
    ).all()
    out: dict[str, list[tuple[date, str, float]]] = {}
    for cid, pe, concept, v in rows:
        kind = "ni" if concept in ni_concepts else "sh"
        out.setdefault(cid, []).append((pe, kind, float(v)))
    return out


def _load_close_history(
    db: Session, company_ids: list[str], start: date, end: date,
) -> dict[str, dict[date, float]]:
    """预拉 close 历史 {company_id: {date: close}}（取每家 company 第一个 security）"""
    # 先取 security_id 映射
    sec_rows = db.execute(
        select(Security.company_id, Security.security_id)
        .where(Security.company_id.in_(company_ids))
        .order_by(Security.company_id, Security.security_id)
    ).all()
    company_to_sec: dict[str, str] = {}
    for cid, sid in sec_rows:
        company_to_sec.setdefault(cid, sid)  # 第一个

    if not company_to_sec:
        return {}

    bar_rows = db.execute(
        select(MarketBar.security_id, MarketBar.trade_date, MarketBar.close)
        .where(
            and_(
                MarketBar.security_id.in_(company_to_sec.values()),
                MarketBar.trade_date >= start,
                MarketBar.trade_date <= end,
                MarketBar.close.isnot(None),
                MarketBar.close > 0,
            )
        )
    ).all()

    sec_to_company = {v: k for k, v in company_to_sec.items()}
    out: dict[str, dict[date, float]] = {}
    for sid, d, c in bar_rows:
        cid = sec_to_company.get(sid)
        if cid is None:
            continue
        out.setdefault(cid, {})[d] = float(c)
    return out


# ---------------- 点时判定 ----------------

def _latest_value_before(
    series: list[tuple[date, float]], cutoff: date
) -> Optional[tuple[date, float]]:
    """在序列中取 ≤ cutoff 的最新 (date, value)。序列假定已按 date 升序。"""
    out = None
    for d, v in series:
        if d <= cutoff:
            out = (d, v)
        else:
            break
    return out


def _close_on_or_before(
    close_map: dict[date, float], cutoff: date, lookback_days: int = 14
) -> Optional[float]:
    """在 close_map 中取 ≤ cutoff 的最新 close。"""
    if not close_map:
        return None
    earliest = cutoff - timedelta(days=lookback_days)
    best_d: Optional[date] = None
    for d in close_map:
        if earliest <= d <= cutoff and (best_d is None or d > best_d):
            best_d = d
    return close_map.get(best_d) if best_d else None


def _evaluate_pit(
    company_id: str,
    rebalance_date: date,
    roce_hist: dict[str, list[tuple[date, float]]],
    lev_hist: dict[str, dict[date, dict[str, float]]],
    ni_sh: dict[str, list[tuple[date, str, float]]],
    close_map_by_cid: dict[str, dict[date, float]],
    *,
    roce_threshold: float,
    pe_max: float,
    nd_ebit_max: float,
    int_cov_min: float,
    lookback_days: int,
) -> Optional[dict]:
    """点时判定单家公司在 rebalance_date 的入选状态与指标。

    返回 dict 含 status / pe_ttm / roce_5y_median 等；不可计算时返回 None。
    """
    cutoff = rebalance_date - timedelta(days=lookback_days)

    # ===== Q3: 5Y ROCE 中位数 + 4/5 年达标 =====
    series = roce_hist.get(company_id, [])
    valid_5y = [v for d, v in series if d <= cutoff][-5:]
    if len(valid_5y) < 5:
        return None
    roce_5y = statistics.median(valid_5y)
    count_ge = sum(1 for v in valid_5y if v >= roce_threshold)
    q_passed = roce_5y >= roce_threshold and count_ge >= 4

    # ===== R1: net_debt/EBIT + interest_coverage（最近年报） =====
    lev = lev_hist.get(company_id, {})
    recent_lev_dates = sorted([d for d in lev if d <= cutoff], reverse=True)
    nd_ebit = None
    int_cov = None
    if recent_lev_dates:
        latest = recent_lev_dates[0]
        nd_ebit = lev[latest].get("net_debt_ebit")
        int_cov = lev[latest].get("interest_coverage")
    r1_pass = True
    if nd_ebit is not None and nd_ebit > nd_ebit_max:
        r1_pass = False
    if int_cov is not None and int_cov < int_cov_min:
        r1_pass = False

    # ===== V: pe_ttm =====
    close = _close_on_or_before(close_map_by_cid.get(company_id, {}), rebalance_date)
    if close is None:
        return None

    # 最近年报 NI 和 shares
    rows = ni_sh.get(company_id, [])
    ni_rows = sorted([(d, v) for d, kind, v in rows if kind == "ni" and d <= cutoff], reverse=True)
    sh_rows = sorted([(d, v) for d, kind, v in rows if kind == "sh" and d <= cutoff], reverse=True)
    if not ni_rows or not sh_rows:
        return None
    ni_value = ni_rows[0][1]
    sh_value = sh_rows[0][1]
    if ni_value <= 0 or sh_value <= 0:
        return None

    market_cap = close * sh_value
    pe_ttm = market_cap / ni_value

    v_state = "Cheap" if pe_ttm <= pe_max else "TooExpensive"

    # ===== 五状态裁决（简化版）=====
    if not q_passed:
        status = "Rejected"
    elif not r1_pass:
        status = "Rejected"
    elif v_state == "TooExpensive":
        status = "TooExpensive"
    else:
        status = "NearFairPrice"

    return {
        "company_id": company_id,
        "status": status,
        "roce_5y_median": roce_5y,
        "count_ge_threshold": count_ge,
        "pe_ttm": pe_ttm,
        "market_cap": market_cap,
        "net_debt_ebit": nd_ebit,
        "interest_coverage": int_cov,
        "close": close,
    }


# ---------------- 月度回测主入口 ----------------

def monthly_rebalance(
    *,
    market: str = "US",
    start: date = date(2020, 1, 1),
    end: date = date(2024, 12, 31),
    roce_threshold: float = DEFAULT_ROCE_THRESHOLD,
    pe_max: float = DEFAULT_PE_MAX,
    nd_ebit_max: float = DEFAULT_R1_NET_DEBT_EBIT_MAX,
    int_cov_min: float = DEFAULT_R1_INTEREST_COVERAGE_MIN,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> BacktestReport:
    """主入口。"""
    db = SessionLocal()
    try:
        # 1. universe
        cid_rows = db.execute(
            select(Company.company_id).where(Company.market == market)
        ).all()
        company_ids = [r[0] for r in cid_rows]

        # 2. 交易日历 → month_starts
        trading_days = _list_us_trading_days(db, start, end)
        if not trading_days:
            raise ValueError(f"无 {market} 交易日历数据，区间 {start}-{end}")
        months = _month_starts(trading_days)

        # 3. 预拉所有数据
        log.info("预拉 ROCE / leverage / NI/shares / close ...")
        roce_hist = _load_roce_history(db, company_ids)
        lev_hist = _load_leverage_history(db, company_ids)
        ni_sh = _load_ni_shares(db, company_ids, market)
        close_map_by_cid = _load_close_history(db, company_ids, start, end + timedelta(days=35))

        # 4. 月度循环
        report = BacktestReport(
            market=market, start=start, end=end,
            universe_size=len(company_ids),
            roce_threshold=roce_threshold, pe_max=pe_max,
        )
        nav = 1.0
        report.nav_series.append((months[0], nav))

        for i, rebalance_date in enumerate(months):
            snap = MonthlySnapshot(rebalance_date=rebalance_date)
            # 4.1 评估每家公司
            results = []
            for cid in company_ids:
                r = _evaluate_pit(
                    cid, rebalance_date,
                    roce_hist, lev_hist, ni_sh, close_map_by_cid,
                    roce_threshold=roce_threshold, pe_max=pe_max,
                    nd_ebit_max=nd_ebit_max, int_cov_min=int_cov_min,
                    lookback_days=lookback_days,
                )
                if r:
                    results.append(r)
            candidates = [r for r in results if r["status"] == "NearFairPrice"]
            snap.candidates = candidates

            # 4.2 持有到下月初，计算月度回报
            if i + 1 < len(months) and candidates:
                next_date = months[i + 1]
                stock_returns = []
                for c in candidates:
                    cur = c["close"]
                    nxt = _close_on_or_before(close_map_by_cid.get(c["company_id"], {}), next_date)
                    if cur and nxt:
                        stock_returns.append(nxt / cur - 1.0)
                if stock_returns:
                    monthly_ret = sum(stock_returns) / len(stock_returns)
                    snap.return_pct = monthly_ret
                    nav *= (1 + monthly_ret)
                    report.monthly_returns.append((rebalance_date, monthly_ret))
            snap.nav = nav
            report.nav_series.append((rebalance_date, nav))
            report.snapshots.append(snap)
            if (i + 1) % 12 == 0:
                log.info("rebalance %d/%d (%s) candidates=%d nav=%.3f",
                         i + 1, len(months), rebalance_date, len(candidates), nav)

        # 5. 汇总指标
        report.total_return = nav - 1.0
        years = (end - start).days / 365.25
        report.cagr = annualize_return(report.total_return, years)
        if report.monthly_returns:
            rets = [r for _, r in report.monthly_returns]
            report.win_rate_months = win_rate(rets)
            if len(rets) > 1:
                mean_r = safe_mean(rets)
                std_r = statistics.stdev(rets)
                if std_r > 0:
                    report.sharpe = (mean_r / std_r) * math.sqrt(12)  # 月度 → 年化

        # MaxDD
        peak = 1.0
        max_dd = 0.0
        for _, v in report.nav_series:
            if v > peak:
                peak = v
            dd = (v / peak) - 1.0
            if dd < max_dd:
                max_dd = dd
        report.max_drawdown = max_dd

        return report
    finally:
        db.close()


def report_to_dict(report: BacktestReport) -> dict:
    return {
        "market": report.market,
        "start": report.start.isoformat(),
        "end": report.end.isoformat(),
        "universe_size": report.universe_size,
        "roce_threshold": report.roce_threshold,
        "pe_max": report.pe_max,
        "total_return": report.total_return,
        "cagr": report.cagr,
        "sharpe": report.sharpe,
        "max_drawdown": report.max_drawdown,
        "win_rate_months": report.win_rate_months,
        "n_months": len(report.monthly_returns),
        "nav_series": [(d.isoformat(), v) for d, v in report.nav_series],
        "monthly_returns": [(d.isoformat(), r) for d, r in report.monthly_returns],
        "snapshots": [
            {
                "rebalance_date": s.rebalance_date.isoformat(),
                "n_candidates": len(s.candidates),
                "return_pct": s.return_pct,
                "nav": s.nav,
                "top_candidates": [
                    {k: c[k] for k in ("company_id", "roce_5y_median", "pe_ttm")}
                    for c in s.candidates[:10]
                ],
            }
            for s in report.snapshots
        ],
    }


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Darwen V2 月度滚动回测")
    parser.add_argument("--market", default="US")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--roce", type=float, default=DEFAULT_ROCE_THRESHOLD)
    parser.add_argument("--pe", type=float, default=DEFAULT_PE_MAX)
    args = parser.parse_args()

    report = monthly_rebalance(
        market=args.market,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        roce_threshold=args.roce,
        pe_max=args.pe,
    )

    out = report_to_dict(report)
    # 概览不打长 series
    summary = {k: v for k, v in out.items() if k not in ("nav_series", "monthly_returns", "snapshots")}
    summary["n_months"] = out["n_months"]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f'\n月度候选数（每 6 月一次抽样）:')
    for s in out["snapshots"][::6]:
        nav_str = f'{s["nav"]:.3f}' if s["nav"] is not None else "n/a"
        print(f'  {s["rebalance_date"]}: candidates={s["n_candidates"]} nav={nav_str}')
