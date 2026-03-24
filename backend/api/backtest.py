# -*- coding: utf-8 -*-
"""回测 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.backtest.runner import run_backtest

router = APIRouter(prefix="/v1", tags=["backtest"])


@router.get("/backtest")
def backtest(
    start_year: int = Query(2020),
    end_year: int = Query(2024),
    model: str = Query("balanced"),
    market: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """运行回测"""
    return run_backtest(db, start_year, end_year, model, market)
