# -*- coding: utf-8 -*-
"""最小回测模块：季度调仓，Top 等权 vs 全市场"""
import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from backend.models import ScoreSnapshot, Company, MarketBar, Security


def get_quarterly_dates(start_year: int, end_year: int) -> list[date]:
    """生成季度调仓日期（每季度末）"""
    dates = []
    for y in range(start_year, end_year + 1):
        for m in [3, 6, 9, 12]:
            # 季末后 45 天调仓（等财报披露）
            rebal_date = date(y, m, 28) + timedelta(days=45)
            if rebal_date.year > end_year:
                break
            dates.append(rebal_date)
    return dates


def get_top_companies(db: Session, asof: date, model: str = "balanced", market: Optional[str] = None) -> list[str]:
    """获取某日期 Top 层公司列表"""
    stmt = (
        select(ScoreSnapshot.company_id)
        .where(and_(
            ScoreSnapshot.asof_date == asof,
            ScoreSnapshot.model_version == model,
            ScoreSnapshot.tier == "Top",
        ))
    )
    if market:
        stmt = stmt.join(Company, Company.company_id == ScoreSnapshot.company_id)
        stmt = stmt.where(Company.market == market)

    return [row[0] for row in db.execute(stmt).fetchall()]


def get_price(db: Session, company_id: str, target_date: date, window_days: int = 10) -> Optional[float]:
    """获取某公司在目标日期附近的收盘价"""
    stmt = (
        select(MarketBar.close)
        .join(Security, Security.security_id == MarketBar.security_id)
        .where(and_(
            Security.company_id == company_id,
            MarketBar.trade_date >= target_date - timedelta(days=window_days),
            MarketBar.trade_date <= target_date + timedelta(days=window_days),
        ))
        .order_by(MarketBar.trade_date.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    return row[0] if row else None


def run_backtest(
    db: Session,
    start_year: int = 2020,
    end_year: int = 2024,
    model: str = "balanced",
    market: Optional[str] = None,
    initial_capital: float = 1_000_000.0,
    transaction_cost: float = 0.001,
) -> dict:
    """
    运行最小回测：
    - 季度调仓
    - Top 等权组合
    - 计算 CAGR, 最大回撤, Sharpe
    """
    rebal_dates = get_quarterly_dates(start_year, end_year)
    logger.info(f"回测参数: {start_year}-{end_year}, model={model}, market={market}, 调仓日={len(rebal_dates)}")

    portfolio_values = []
    capital = initial_capital
    holdings = {}  # company_id -> shares

    for i, rebal_date in enumerate(rebal_dates):
        # 1. 获取 Top 层
        top_companies = get_top_companies(db, rebal_date, model, market)

        if not top_companies:
            portfolio_values.append({"date": str(rebal_date), "value": capital})
            continue

        # 2. 清算当前持仓
        if holdings:
            sell_proceeds = 0.0
            for cid, shares in holdings.items():
                price = get_price(db, cid, rebal_date)
                if price and shares:
                    sell_proceeds += price * shares * (1 - transaction_cost)
            if sell_proceeds > 0:
                capital = sell_proceeds
            holdings = {}

        # 3. 等权买入 Top
        per_stock = capital / len(top_companies)
        for cid in top_companies:
            price = get_price(db, cid, rebal_date)
            if price and price > 0:
                shares = (per_stock * (1 - transaction_cost)) / price
                holdings[cid] = shares
                capital -= per_stock

        # 记录组合价值
        total_value = capital
        for cid, shares in holdings.items():
            price = get_price(db, cid, rebal_date)
            if price:
                total_value += price * shares

        portfolio_values.append({"date": str(rebal_date), "value": total_value})

    # 计算绩效指标
    if len(portfolio_values) < 2:
        return {
            "portfolio_values": portfolio_values,
            "metrics": {"error": "数据不足，无法计算指标"},
        }

    values = [pv["value"] for pv in portfolio_values]
    years = (end_year - start_year) or 1

    # CAGR
    cagr_val = (values[-1] / values[0]) ** (1.0 / years) - 1.0 if values[0] > 0 else None

    # 最大回撤
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Sharpe (简化：用季度收益率, 无风险利率 0)
    returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            returns.append(values[i] / values[i - 1] - 1)

    sharpe = None
    if returns:
        arr = np.array(returns)
        mean_ret = np.mean(arr)
        std_ret = np.std(arr)
        if std_ret > 0:
            sharpe = float(mean_ret / std_ret * math.sqrt(4))  # 年化（4个季度）

    metrics = {
        "start_value": values[0],
        "end_value": values[-1],
        "total_return": f"{((values[-1] / values[0]) - 1) * 100:.2f}%",
        "cagr": f"{cagr_val * 100:.2f}%" if cagr_val else "N/A",
        "max_drawdown": f"{max_dd * 100:.2f}%",
        "sharpe_ratio": f"{sharpe:.2f}" if sharpe else "N/A",
        "rebalance_count": len(rebal_dates),
        "quarters_with_holdings": sum(1 for pv in portfolio_values if pv["value"] != initial_capital),
    }

    logger.info(f"回测完成: CAGR={metrics['cagr']}, MaxDD={metrics['max_drawdown']}, Sharpe={metrics['sharpe_ratio']}")

    return {
        "params": {
            "start_year": start_year,
            "end_year": end_year,
            "model": model,
            "market": market,
            "initial_capital": initial_capital,
        },
        "portfolio_values": portfolio_values,
        "metrics": metrics,
    }
