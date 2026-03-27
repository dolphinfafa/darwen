# -*- coding: utf-8 -*-
"""筛选 API"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc, asc

from backend.database import get_db
from backend.models import ScoreSnapshot, Company, Security
from backend.schemas.common import ScoreResponse

router = APIRouter(prefix="/v1", tags=["screener"])


@router.get("/screener", response_model=list[ScoreResponse])
def screener(
    market: Optional[str] = Query(None, description="US 或 CN_A"),
    industry: Optional[str] = Query(None),
    tier: Optional[str] = Query(None, description="Top/Watch/Reject"),
    model: str = Query("balanced", description="balanced/conservative/aggressive"),
    asof: Optional[date] = Query(None),
    sort_by: str = Query("total", description="排序字段"),
    sort_desc: bool = Query(True),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """股票筛选：按评分分层、市场、行业过滤"""
    stmt = (
        select(
            ScoreSnapshot,
            Company.name,
            Company.market,
            Company.industry_name,
        )
        .join(Company, Company.company_id == ScoreSnapshot.company_id)
        .where(ScoreSnapshot.model_version == model)
    )

    if market:
        stmt = stmt.where(Company.market == market)
    if industry:
        stmt = stmt.where(Company.industry_name.contains(industry))
    if tier:
        stmt = stmt.where(ScoreSnapshot.tier == tier)
    if asof:
        stmt = stmt.where(ScoreSnapshot.asof_date == asof)

    # 排序
    sort_col = getattr(ScoreSnapshot, sort_by, ScoreSnapshot.total)
    stmt = stmt.order_by(desc(sort_col) if sort_desc else asc(sort_col))
    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()

    results = []
    for ss, name, mkt, ind_name in rows:
        results.append(ScoreResponse(
            company_id=ss.company_id,
            name=name,
            market=mkt,
            industry_name=ind_name,
            asof_date=ss.asof_date,
            model_version=ss.model_version,
            survival=ss.survival,
            replication=ss.replication,
            adaptation=ss.adaptation,
            moat=ss.moat,
            valuation=ss.valuation,
            total=ss.total,
            tier=ss.tier,
            gating_flags=ss.gating_flags,
        ))

    return results
