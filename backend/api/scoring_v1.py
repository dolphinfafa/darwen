# -*- coding: utf-8 -*-
"""V1.0 评分 API — 达尔文流程模型"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Company

router = APIRouter(prefix="/v1", tags=["scoring-v1"])


@router.get("/company/{company_id}/score-v1")
def company_score_v1(
    company_id: str,
    asof: date = Query(None),
    db: Session = Depends(get_db),
):
    """V1.0 达尔文流程模型评分详情"""
    from backend.scoring.engine_v1 import score_company_v1

    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, f"公司 {company_id} 不存在")

    if not asof:
        asof = date(2024, 12, 31)

    result = score_company_v1(db, company_id, asof, company.market)
    return result


@router.post("/batch-score-v1")
def batch_score_v1(
    market: str = Query("US"),
    asof: str = Query("2024-12-31"),
    db: Session = Depends(get_db),
):
    """批量运行 V1.0 评分"""
    from backend.scoring.engine_v1 import score_company_v1
    from sqlalchemy import select

    asof_date = date.fromisoformat(asof)
    companies = db.execute(
        select(Company.company_id).where(Company.market == market)
    ).scalars().all()

    results = {"total": len(companies), "scored": 0, "rejected": 0, "errors": 0}
    for cid in companies:
        try:
            r = score_company_v1(db, cid, asof_date, market)
            if r["status"] == "REJECT":
                results["rejected"] += 1
            results["scored"] += 1
        except Exception as e:
            results["errors"] += 1

    return results
