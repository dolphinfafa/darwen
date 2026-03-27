# -*- coding: utf-8 -*-
"""
Darwen 回测引擎 V2
- 时间切片回测（季度/年度调仓）
- 五档分层验证（Quintile Ranking）
- 组合收益计算（CAGR / Sharpe / MaxDD / Alpha）
"""
import math
from datetime import date, timedelta
from collections import defaultdict

import numpy as np
from loguru import logger
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from backend.models import Company, Security, ScoreSnapshot, FactorValue, MarketBar


# ── 工具函数 ───────────────────────────────────────

def get_price_near(db: Session, security_id: str, target: date, window: int = 15) -> float | None:
    """取 target 附近最近的收盘价"""
    row = db.execute(
        select(MarketBar.close)
        .where(and_(
            MarketBar.security_id == security_id,
            MarketBar.trade_date.between(target - timedelta(days=window), target + timedelta(days=window)),
            MarketBar.close.isnot(None),
        ))
        .order_by(func.abs(func.datediff(MarketBar.trade_date, target)))
        .limit(1)
    ).scalar()
    return float(row) if row is not None else None


def get_security_id(db: Session, company_id: str) -> str | None:
    sec = db.execute(
        select(Security.security_id).where(Security.company_id == company_id).limit(1)
    ).scalar()
    return sec


def get_rebalance_dates(start_year: int, end_year: int, freq: str = "yearly") -> list[date]:
    """生成调仓日期序列"""
    dates = []
    if freq == "quarterly":
        for y in range(start_year, end_year + 1):
            for m in [3, 6, 9, 12]:
                # 季末 + 45 天（财报披露延迟）
                d = date(y, m, 28) + timedelta(days=45)
                if d <= date(end_year, 12, 31) + timedelta(days=45):
                    dates.append(d)
    else:  # yearly
        for y in range(start_year, end_year + 1):
            dates.append(date(y, 12, 31))
    return dates


# ── 核心：分层回测 ─────────────────────────────────

def run_quintile_backtest(
    db: Session,
    start_year: int = 2013,
    end_year: int = 2024,
    model: str = "balanced",
    market: str = "US",
    n_groups: int = 5,
    transaction_cost: float = 0.002,
) -> dict:
    """
    分层回测：按评分分成 N 组，计算各组的持有期收益。

    Returns: {
        "params": {...},
        "periods": [{date, groups: [{label, count, avg_score, return, ...}]}],
        "summary": {group_label: {avg_return, cumulative, sharpe, ...}},
        "portfolio_curve": [{date, value, benchmark}],
    }
    """
    periods = []
    group_returns = defaultdict(list)  # label -> [return, ...]
    group_labels = [f"Q{i+1}({'高' if i == 0 else '低' if i == n_groups - 1 else '中'})" for i in range(n_groups)]

    # 组合净值曲线
    portfolio_values = []  # top group
    benchmark_values = []  # equal weight all
    top_nav = 1.0
    bench_nav = 1.0

    rebalance_dates = get_rebalance_dates(start_year, end_year - 1, freq="yearly")

    for i, asof in enumerate(rebalance_dates):
        # 下一期日期
        next_date = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else date(end_year, 12, 31)

        # 取该期所有评分
        snapshots = db.execute(
            select(ScoreSnapshot)
            .join(Company, Company.company_id == ScoreSnapshot.company_id)
            .where(and_(
                ScoreSnapshot.asof_date == asof,
                ScoreSnapshot.model_version == model,
                ScoreSnapshot.total.isnot(None),
                Company.market == market,
            ))
            .order_by(ScoreSnapshot.total.desc())
        ).scalars().all()

        if len(snapshots) < n_groups:
            logger.warning(f"{asof}: 仅 {len(snapshots)} 只股票，跳过")
            continue

        # 分组
        group_size = len(snapshots) // n_groups
        groups_data = []

        for g in range(n_groups):
            start_idx = g * group_size
            end_idx = start_idx + group_size if g < n_groups - 1 else len(snapshots)
            group_stocks = snapshots[start_idx:end_idx]

            # 计算该组的持有期收益
            returns = []
            for ss in group_stocks:
                sec_id = get_security_id(db, ss.company_id)
                if not sec_id:
                    continue
                buy_price = get_price_near(db, sec_id, asof)
                sell_price = get_price_near(db, sec_id, next_date)
                if buy_price and sell_price and buy_price > 0:
                    ret = (sell_price / buy_price) - 1 - transaction_cost
                    ret = max(min(ret, 5.0), -0.9)  # 截尾
                    returns.append(ret)

            avg_return = float(np.mean(returns)) if returns else 0.0
            avg_score = float(np.mean([ss.total for ss in group_stocks]))

            groups_data.append({
                "label": group_labels[g],
                "count": len(group_stocks),
                "valid_returns": len(returns),
                "avg_score": round(avg_score, 2),
                "avg_return": round(avg_return * 100, 2),  # %
            })

            group_returns[group_labels[g]].append(avg_return)

        # 更新净值曲线
        if groups_data:
            top_ret = groups_data[0]["avg_return"] / 100
            bench_ret = float(np.mean([g["avg_return"] for g in groups_data])) / 100
            top_nav *= (1 + top_ret)
            bench_nav *= (1 + bench_ret)

        portfolio_values.append({"date": str(next_date), "top": round(top_nav, 4), "benchmark": round(bench_nav, 4)})

        periods.append({
            "date": str(asof),
            "next_date": str(next_date),
            "total_stocks": len(snapshots),
            "groups": groups_data,
        })

    # 汇总统计
    summary = {}
    for label in group_labels:
        rets = group_returns[label]
        if not rets:
            continue
        arr = np.array(rets)
        avg = float(np.mean(arr))
        vol = float(np.std(arr)) if len(arr) > 1 else 0.0
        cum = float(np.prod(1 + arr) - 1)
        n_years = len(arr)
        cagr_val = float((1 + cum) ** (1 / max(n_years, 1)) - 1) if cum > -1 else -1.0
        sharpe = float(avg / vol * math.sqrt(1)) if vol > 0 else 0.0
        win_rate = float(np.mean(arr > 0))

        summary[label] = {
            "periods": n_years,
            "avg_annual_return": round(avg * 100, 2),
            "cumulative_return": round(cum * 100, 2),
            "cagr": round(cagr_val * 100, 2),
            "volatility": round(vol * 100, 2),
            "sharpe": round(sharpe, 2),
            "win_rate": round(win_rate * 100, 1),
            "max_return": round(float(np.max(arr)) * 100, 2) if len(arr) > 0 else 0,
            "min_return": round(float(np.min(arr)) * 100, 2) if len(arr) > 0 else 0,
        }

    # 单调性检验
    avg_returns = [summary.get(label, {}).get("avg_annual_return", 0) for label in group_labels]
    is_monotonic = all(avg_returns[i] >= avg_returns[i + 1] for i in range(len(avg_returns) - 1))

    return {
        "params": {
            "start_year": start_year,
            "end_year": end_year,
            "model": model,
            "market": market,
            "n_groups": n_groups,
            "transaction_cost": transaction_cost,
        },
        "periods": periods,
        "summary": summary,
        "portfolio_curve": portfolio_values,
        "monotonic": is_monotonic,
        "verdict": "VALID" if is_monotonic and len(periods) >= 3 else "NEEDS_REVIEW",
    }


# ── 组合回测（Top N 等权） ──────────────────────────

def run_portfolio_backtest(
    db: Session,
    start_year: int = 2013,
    end_year: int = 2024,
    model: str = "balanced",
    market: str = "US",
    top_pct: float = 0.2,
    transaction_cost: float = 0.002,
) -> dict:
    """
    Top N% 等权组合回测，含 benchmark（全市场等权）

    Returns: {portfolio_curve, metrics, holdings_history}
    """
    rebalance_dates = get_rebalance_dates(start_year, end_year - 1, freq="yearly")

    nav = 1.0
    bench_nav = 1.0
    curve = []
    peak = 1.0
    max_dd = 0.0
    annual_returns = []
    bench_annual_returns = []
    holdings_history = []

    for i, asof in enumerate(rebalance_dates):
        next_date = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else date(end_year, 12, 31)

        snapshots = db.execute(
            select(ScoreSnapshot)
            .join(Company, Company.company_id == ScoreSnapshot.company_id)
            .where(and_(
                ScoreSnapshot.asof_date == asof,
                ScoreSnapshot.model_version == model,
                ScoreSnapshot.total.isnot(None),
                Company.market == market,
            ))
            .order_by(ScoreSnapshot.total.desc())
        ).scalars().all()

        if not snapshots:
            continue

        n_top = max(1, int(len(snapshots) * top_pct))
        top_stocks = snapshots[:n_top]

        # Top 组合收益
        top_rets = []
        holdings = []
        for ss in top_stocks:
            sec_id = get_security_id(db, ss.company_id)
            if not sec_id:
                continue
            bp = get_price_near(db, sec_id, asof)
            sp = get_price_near(db, sec_id, next_date)
            if bp and sp and bp > 0:
                r = (sp / bp) - 1 - transaction_cost
                r = max(min(r, 5.0), -0.9)
                top_rets.append(r)
                holdings.append({"company_id": ss.company_id, "score": round(ss.total, 2), "return": round(r * 100, 2)})

        # Benchmark: 全市场等权
        all_rets = []
        for ss in snapshots:
            sec_id = get_security_id(db, ss.company_id)
            if not sec_id:
                continue
            bp = get_price_near(db, sec_id, asof)
            sp = get_price_near(db, sec_id, next_date)
            if bp and sp and bp > 0:
                r = (sp / bp) - 1
                r = max(min(r, 5.0), -0.9)  # 截尾
                all_rets.append(r)

        port_ret = float(np.mean(top_rets)) if top_rets else 0.0
        bench_ret = float(np.mean(all_rets)) if all_rets else 0.0

        nav *= (1 + port_ret)
        bench_nav *= (1 + bench_ret)
        peak = max(peak, nav)
        dd = (peak - nav) / peak
        max_dd = max(max_dd, dd)

        annual_returns.append(port_ret)
        bench_annual_returns.append(bench_ret)

        curve.append({
            "date": str(next_date),
            "portfolio": round(nav, 4),
            "benchmark": round(bench_nav, 4),
            "drawdown": round(-dd * 100, 2),
        })

        holdings_history.append({
            "date": str(asof),
            "n_holdings": len(top_rets),
            "top_holdings": holdings[:10],
        })

    # 指标计算
    arr = np.array(annual_returns) if annual_returns else np.array([0])
    barr = np.array(bench_annual_returns) if bench_annual_returns else np.array([0])
    n_years = len(annual_returns) or 1
    total_return = nav - 1
    cagr_val = (nav ** (1 / n_years)) - 1 if nav > 0 else -1
    vol = float(np.std(arr)) if len(arr) > 1 else 0
    sharpe = float(np.mean(arr) / vol) if vol > 0 else 0
    alpha = float(np.mean(arr) - np.mean(barr))

    metrics = {
        "total_return": round(total_return * 100, 2),
        "cagr": round(cagr_val * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "volatility": round(vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "alpha": round(alpha * 100, 2),
        "win_rate": round(float(np.mean(arr > 0)) * 100, 1),
        "n_periods": n_years,
        "benchmark_cagr": round((bench_nav ** (1 / n_years) - 1) * 100, 2) if bench_nav > 0 else 0,
    }

    return {
        "params": {"start_year": start_year, "end_year": end_year, "model": model, "market": market, "top_pct": top_pct},
        "curve": curve,
        "metrics": metrics,
        "holdings_history": holdings_history,
    }
