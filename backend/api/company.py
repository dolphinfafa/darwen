# -*- coding: utf-8 -*-
"""公司详情 API"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from backend.database import get_db
from backend.models import Company, Security, ScoreSnapshot, FactorValue, MarketBar
from backend.schemas.common import (
    CompanyBrief, ScoreResponse, FactorDetail, CompanyScoreDetail,
    PricePoint, ScorePoint, CompanyHistory, LatestPrice,
)

router = APIRouter(prefix="/v1", tags=["company"])


@router.get("/company/{company_id}/score", response_model=CompanyScoreDetail)
def company_score_detail(
    company_id: str,
    model: str = Query("balanced"),
    asof: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """单只股票评分详情：五维分 + 因子明细 + 数据溯源"""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, f"公司 {company_id} 不存在")

    # 获取 ticker
    sec = db.execute(
        select(Security).where(Security.company_id == company_id).limit(1)
    ).scalar()

    brief = CompanyBrief(
        company_id=company.company_id,
        market=company.market,
        name=company.name,
        name_en=company.name_en,
        industry_name=company.industry_name,
        ticker=sec.ticker if sec else None,
    )

    # 获取评分快照
    ss_stmt = select(ScoreSnapshot).where(and_(
        ScoreSnapshot.company_id == company_id,
        ScoreSnapshot.model_version == model,
    ))
    if asof:
        ss_stmt = ss_stmt.where(ScoreSnapshot.asof_date == asof)
    ss_stmt = ss_stmt.order_by(ScoreSnapshot.asof_date.desc()).limit(1)

    snapshot = db.execute(ss_stmt).scalar()
    if not snapshot:
        raise HTTPException(404, f"公司 {company_id} 无评分数据")

    score = ScoreResponse(
        company_id=snapshot.company_id,
        name=company.name,
        market=company.market,
        asof_date=snapshot.asof_date,
        model_version=snapshot.model_version,
        survival=snapshot.survival,
        replication=snapshot.replication,
        adaptation=snapshot.adaptation,
        moat=snapshot.moat,
        valuation=snapshot.valuation,
        total=snapshot.total,
        tier=snapshot.tier,
        gating_flags=snapshot.gating_flags,
    )

    # 获取因子明细
    fv_stmt = select(FactorValue).where(and_(
        FactorValue.company_id == company_id,
        FactorValue.asof_date == snapshot.asof_date,
    )).order_by(FactorValue.factor_code)

    factors = [
        FactorDetail(
            factor_code=fv.factor_code,
            raw_value=fv.raw_value,
            score=fv.score,
            lineage=fv.lineage,
        )
        for fv in db.execute(fv_stmt).scalars().all()
    ]

    # 获取最新股价
    latest_price = None
    if sec:
        currency = company.currency or ("CNY" if company.market == "CN_A" else "USD")
        # A股：取不复权实时价格
        if company.market == "CN_A" and sec.ticker:
            try:
                import akshare as ak
                df = ak.stock_zh_a_hist(
                    symbol=sec.ticker, period="daily",
                    start_date="20260101", adjust="",
                )
                if df is not None and not df.empty:
                    last_row = df.iloc[-1]
                    import pandas as pd
                    latest_price = LatestPrice(
                        date=pd.to_datetime(last_row["日期"]).date(),
                        close=round(float(last_row["收盘"]), 2),
                        currency=currency,
                    )
            except Exception:
                pass
        # 美股/兜底：从 MarketBar 取
        if not latest_price:
            bar = db.execute(
                select(MarketBar.trade_date, MarketBar.close)
                .where(and_(
                    MarketBar.security_id == sec.security_id,
                    MarketBar.close.isnot(None),
                ))
                .order_by(MarketBar.trade_date.desc())
                .limit(1)
            ).first()
            if bar:
                latest_price = LatestPrice(
                    date=bar[0],
                    close=round(bar[1], 2),
                    currency=currency,
                )

    return CompanyScoreDetail(company=brief, score=score, factors=factors, latest_price=latest_price)


@router.get("/company/{company_id}/history", response_model=CompanyHistory)
def company_history(
    company_id: str,
    model: str = Query("balanced"),
    db: Session = Depends(get_db),
):
    """股票历史价格 + 历史评分时间序列"""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, f"公司 {company_id} 不存在")

    sec = db.execute(
        select(Security).where(Security.company_id == company_id).limit(1)
    ).scalar()

    # 历史价格：按月采样（每月最后一条）
    prices = []
    if sec:
        bars = db.execute(
            select(MarketBar.trade_date, MarketBar.close)
            .where(and_(
                MarketBar.security_id == sec.security_id,
                MarketBar.close.isnot(None),
            ))
            .order_by(MarketBar.trade_date)
        ).all()
        # 按月采样：取每月最后一个交易日
        monthly = {}
        for trade_date, close in bars:
            key = (trade_date.year, trade_date.month)
            monthly[key] = PricePoint(date=trade_date, close=round(close, 2))
        prices = sorted(monthly.values(), key=lambda p: p.date)

    # 历史评分
    snapshots = db.execute(
        select(ScoreSnapshot)
        .where(and_(
            ScoreSnapshot.company_id == company_id,
            ScoreSnapshot.model_version == model,
        ))
        .order_by(ScoreSnapshot.asof_date)
    ).scalars().all()

    scores = [
        ScorePoint(
            date=s.asof_date,
            total=s.total,
            survival=s.survival,
            replication=s.replication,
            adaptation=s.adaptation,
            moat=s.moat,
            valuation=s.valuation,
            tier=s.tier,
        )
        for s in snapshots
    ]

    return CompanyHistory(
        company_id=company_id,
        ticker=sec.ticker if sec else None,
        prices=prices,
        scores=scores,
    )


@router.get("/companies", response_model=list[CompanyBrief])
def list_companies(
    market: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="搜索公司名或代码"),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """公司列表"""
    stmt = select(Company, Security.ticker).outerjoin(
        Security, Security.company_id == Company.company_id
    )
    if market:
        stmt = stmt.where(Company.market == market)
    if search:
        stmt = stmt.where(
            Company.name.contains(search) |
            Company.company_id.contains(search)
        )
    stmt = stmt.limit(limit)

    results = []
    for c, ticker in db.execute(stmt).all():
        results.append(CompanyBrief(
            company_id=c.company_id,
            market=c.market,
            name=c.name,
            name_en=c.name_en,
            industry_name=c.industry_name,
            ticker=ticker,
        ))

    return results
