# -*- coding: utf-8 -*-
"""批量报告 API"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from backend.database import get_db
from backend.models import ScoreSnapshot, Company
from backend.scoring.weights import MODEL_NAMES

router = APIRouter(prefix="/v1", tags=["report"])


@router.get("/reports/batch")
def batch_report(
    market: Optional[str] = Query(None),
    model: str = Query("balanced"),
    tier: Optional[str] = Query(None),
    asof: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """批量报告：返回汇总统计 + 公司列表"""
    stmt = (
        select(ScoreSnapshot, Company.name, Company.market, Company.industry_name)
        .join(Company, Company.company_id == ScoreSnapshot.company_id)
        .where(ScoreSnapshot.model_version == model)
    )
    if market:
        stmt = stmt.where(Company.market == market)
    if tier:
        stmt = stmt.where(ScoreSnapshot.tier == tier)
    if asof:
        stmt = stmt.where(ScoreSnapshot.asof_date == asof)

    rows = db.execute(stmt).all()

    # 统计
    tier_counts = {"Top": 0, "Watch": 0, "Reject": 0}
    industry_dist = {}
    companies = []

    for ss, name, mkt, ind in rows:
        t = ss.tier or "Reject"
        tier_counts[t] = tier_counts.get(t, 0) + 1
        if ind:
            industry_dist[ind] = industry_dist.get(ind, 0) + 1

        companies.append({
            "company_id": ss.company_id,
            "name": name,
            "market": mkt,
            "industry": ind,
            "total": ss.total,
            "tier": ss.tier,
            "survival": ss.survival,
            "replication": ss.replication,
            "adaptation": ss.adaptation,
            "moat": ss.moat,
            "valuation": ss.valuation,
        })

    return {
        "summary": {
            "total_companies": len(companies),
            "tier_distribution": tier_counts,
            "industry_distribution": industry_dist,
            "model": model,
        },
        "companies": companies,
    }


@router.get("/meta/models")
def list_models():
    """可用权重方案"""
    return {"models": MODEL_NAMES}


@router.get("/meta/industries")
def list_industries(db: Session = Depends(get_db)):
    """行业列表"""
    from backend.models import Company
    stmt = select(Company.industry_name).distinct().where(Company.industry_name.isnot(None))
    industries = [row[0] for row in db.execute(stmt).fetchall()]
    return {"industries": sorted(industries)}
