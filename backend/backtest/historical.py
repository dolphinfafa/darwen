# -*- coding: utf-8 -*-
"""历史回测：在多个年末时间点评分，追踪远期收益，验证评分系统有效性"""
import hashlib
from datetime import date, timedelta

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func

from backend.models import Company, Fact, FactorValue, ScoreSnapshot, Security, MarketBar
from backend.factors.compute import compute_and_store_factors
from backend.scoring.engine import score_company


def get_price_at(db: Session, security_id: str, target_date: date, window: int = 15) -> float | None:
    """获取某日附近最近的收盘价"""
    stmt = (
        select(MarketBar.close, MarketBar.trade_date)
        .where(and_(
            MarketBar.security_id == security_id,
            MarketBar.trade_date >= target_date - timedelta(days=window),
            MarketBar.trade_date <= target_date + timedelta(days=window),
        ))
        .order_by(func.abs(func.datediff(MarketBar.trade_date, target_date)))
        .limit(1)
    )
    row = db.execute(stmt).first()
    return float(row[0]) if row and row[0] else None


def compute_forward_return(db: Session, company_id: str, score_date: date, months: int = 12) -> float | None:
    """计算评分日后 N 个月的收益率"""
    sec = db.execute(
        select(Security).where(Security.company_id == company_id).limit(1)
    ).scalar()
    if not sec:
        return None

    buy_price = get_price_at(db, sec.security_id, score_date)
    sell_date = date(score_date.year + (months // 12), score_date.month, 28)
    sell_price = get_price_at(db, sec.security_id, sell_date)

    if buy_price and sell_price and buy_price > 0:
        return (sell_price / buy_price) - 1.0
    return None


def run_historical_backtest(
    db: Session,
    start_year: int = 2012,
    end_year: int = 2024,
    market: str = "US",
    model: str = "balanced",
) -> dict:
    """
    历史回测主流程：
    1. 在每个年末时间点，用当时可得数据计算因子+评分
    2. 追踪各层级 1 年期远期收益
    3. 验证 Top > Watch > Reject
    """
    results_by_year = []

    for year in range(start_year, end_year):
        asof = date(year, 12, 31)
        forward_end = date(year + 1, 12, 31)
        logger.info(f"=== 回测年份 {year} (asof={asof}, forward→{forward_end}) ===")

        # 获取该市场所有公司
        companies = db.query(Company).filter_by(market=market).all()
        if not companies:
            continue

        # 检查哪些公司在该年末有数据
        valid_companies = []
        for c in companies:
            fact_count = db.execute(
                select(func.count(Fact.fact_id)).where(and_(
                    Fact.company_id == c.company_id,
                    Fact.period_end <= asof,
                    Fact.period_end >= date(year - 2, 1, 1),
                ))
            ).scalar()
            if fact_count and fact_count >= 5:  # 至少有 5 条近期数据
                valid_companies.append(c)

        if len(valid_companies) < 10:
            logger.warning(f"{year}: 有效公司仅 {len(valid_companies)} 家，跳过")
            continue

        logger.info(f"{year}: {len(valid_companies)} 家有效公司")

        # 清除该年份的旧因子和评分
        for c in valid_companies:
            db.query(FactorValue).filter_by(company_id=c.company_id, asof_date=asof).delete()
        db.query(ScoreSnapshot).filter(and_(
            ScoreSnapshot.asof_date == asof,
            ScoreSnapshot.model_version == model,
        )).delete()
        db.commit()

        # 计算因子
        for c in valid_companies:
            compute_and_store_factors(db, c.company_id, asof)

        # 评分（先用固定阈值打分，再动态分层）
        for c in valid_companies:
            score_company(db, c.company_id, asof, model, market)

        # 动态分位数分层
        from backend.scoring.engine import batch_classify_tiers
        thresholds = batch_classify_tiers(db, asof, model)
        if thresholds:
            logger.info(f"{year} 动态阈值: Top>={thresholds['top_threshold']:.1f}, Watch>={thresholds['watch_threshold']:.1f}")

        # 收集评分结果 + 远期收益
        tier_returns = {"Top": [], "Watch": [], "Reject": []}

        snapshots = db.query(ScoreSnapshot).filter(and_(
            ScoreSnapshot.asof_date == asof,
            ScoreSnapshot.model_version == model,
        )).all()

        for ss in snapshots:
            ret = compute_forward_return(db, ss.company_id, asof, 12)
            tier = ss.tier or "Reject"
            if ret is not None:
                tier_returns[tier].append(ret)

        # 计算各层平均收益
        year_result = {
            "year": year,
            "asof": str(asof),
            "valid_companies": len(valid_companies),
            "tier_counts": {t: len(r) for t, r in tier_returns.items()},
            "tier_avg_return": {},
            "tier_median_return": {},
        }

        for tier, returns in tier_returns.items():
            if returns:
                year_result["tier_avg_return"][tier] = float(np.mean(returns))
                year_result["tier_median_return"][tier] = float(np.median(returns))
            else:
                year_result["tier_avg_return"][tier] = None
                year_result["tier_median_return"][tier] = None

        results_by_year.append(year_result)
        logger.info(
            f"{year} 结果: "
            f"Top({len(tier_returns['Top'])}家)={_fmt_pct(year_result['tier_avg_return'].get('Top'))} | "
            f"Watch({len(tier_returns['Watch'])}家)={_fmt_pct(year_result['tier_avg_return'].get('Watch'))} | "
            f"Reject({len(tier_returns['Reject'])}家)={_fmt_pct(year_result['tier_avg_return'].get('Reject'))}"
        )

    # 汇总统计
    summary = _compute_summary(results_by_year)
    return {"results_by_year": results_by_year, "summary": summary}


def _fmt_pct(v):
    return f"{v*100:.1f}%" if v is not None else "N/A"


def _compute_summary(results: list[dict]) -> dict:
    """汇总所有年份的回测结果"""
    all_returns = {"Top": [], "Watch": [], "Reject": []}

    for r in results:
        for tier in ["Top", "Watch", "Reject"]:
            avg = r["tier_avg_return"].get(tier)
            if avg is not None:
                all_returns[tier].append(avg)

    summary = {}
    for tier, returns in all_returns.items():
        if returns:
            summary[tier] = {
                "years_with_data": len(returns),
                "avg_annual_return": f"{np.mean(returns)*100:.1f}%",
                "median_annual_return": f"{np.median(returns)*100:.1f}%",
                "best_year": f"{max(returns)*100:.1f}%",
                "worst_year": f"{min(returns)*100:.1f}%",
                "win_rate": f"{sum(1 for r in returns if r > 0)/len(returns)*100:.0f}%",
            }
        else:
            summary[tier] = {"years_with_data": 0, "note": "无数据"}

    # 对比：Top 跑赢 Reject 的年份数
    top_returns = all_returns["Top"]
    reject_returns = all_returns["Reject"]
    if top_returns and reject_returns:
        min_len = min(len(top_returns), len(reject_returns))
        outperform = sum(1 for i in range(min_len) if top_returns[i] > reject_returns[i])
        summary["top_vs_reject_outperform"] = f"{outperform}/{min_len} 年"

    watch_returns = all_returns["Watch"]
    if watch_returns and reject_returns:
        min_len = min(len(watch_returns), len(reject_returns))
        outperform = sum(1 for i in range(min_len) if watch_returns[i] > reject_returns[i])
        summary["watch_vs_reject_outperform"] = f"{outperform}/{min_len} 年"

    return summary


if __name__ == "__main__":
    from backend.database import SessionLocal
    import json

    db = SessionLocal()
    try:
        result = run_historical_backtest(db, start_year=2012, end_year=2024, market="US")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    finally:
        db.close()
