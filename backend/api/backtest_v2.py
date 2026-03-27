# -*- coding: utf-8 -*-
"""回测与验证系统 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.backtest.engine_v2 import run_quintile_backtest, run_portfolio_backtest
from backend.backtest.ic_analysis import compute_factor_ic
from backend.backtest.stability import analyze_stability

router = APIRouter(prefix="/v1/backtest-v2", tags=["backtest-v2"])


@router.get("/quintile")
def api_quintile(
    start_year: int = Query(2013),
    end_year: int = Query(2024),
    model: str = Query("balanced"),
    market: str = Query("US"),
    n_groups: int = Query(5, ge=2, le=10),
    db: Session = Depends(get_db),
):
    """分层验证：按评分分 N 组，验证单调性"""
    return run_quintile_backtest(db, start_year, end_year, model, market, n_groups)


@router.get("/portfolio")
def api_portfolio(
    start_year: int = Query(2013),
    end_year: int = Query(2024),
    model: str = Query("balanced"),
    market: str = Query("US"),
    top_pct: float = Query(0.2, ge=0.05, le=0.5),
    db: Session = Depends(get_db),
):
    """组合回测：Top N% 等权 vs 全市场基准"""
    return run_portfolio_backtest(db, start_year, end_year, model, market, top_pct)


@router.get("/factor-ic")
def api_factor_ic(
    start_year: int = Query(2013),
    end_year: int = Query(2024),
    market: str = Query("US"),
    db: Session = Depends(get_db),
):
    """因子有效性分析：IC / ICIR"""
    return compute_factor_ic(db, start_year, end_year, market)


@router.get("/stability")
def api_stability(
    model: str = Query("balanced"),
    market: str = Query("US"),
    db: Session = Depends(get_db),
):
    """评分稳定性分析"""
    return analyze_stability(db, model, market)
