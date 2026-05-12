# -*- coding: utf-8 -*-
"""点时回测 API（M7）。

提供 Bucket Spread 验证：对一次已完成的 screen_run，按 5 状态分桶统计 forward return。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.backtest.bucket_spread import report_to_dict, run_bucket_spread
from backend.backtest.v2_engine import (
    monthly_rebalance,
    report_to_dict as monthly_report_to_dict,
)
from backend.database import get_db
from backend.models.screen_run import ScreenRun
from backend.models.user import User
from backend.services.auth import get_current_user


router = APIRouter(prefix="/v2/backtest", tags=["backtest"])


@router.get("/bucket-spread/{run_id}")
def bucket_spread(
    run_id: int,
    forward_end: date = Query(..., description="forward 终止日，例如 2026-03-27"),
    sample_limit: int = Query(20, ge=2, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对已完成的 screen_run 跑 Bucket Spread：5 状态分桶 vs forward return。

    PRD 第 8 节核心验证指标。
    """
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")
    if run.status != "completed":
        raise HTTPException(400, f"run is {run.status}, must be completed")
    if forward_end <= run.as_of_date:
        raise HTTPException(400, "forward_end 必须晚于 as_of_date")
    try:
        report = run_bucket_spread(run_id, forward_end, sample_limit_per_bucket=sample_limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return report_to_dict(report)


@router.get("/monthly")
def monthly_backtest(
    market: str = Query("US"),
    start: date = Query(..., description="回测起始日 (yyyy-mm-dd)"),
    end: date = Query(..., description="回测终止日"),
    roce_threshold: float = Query(0.20, ge=0.05, le=0.50),
    pe_max: float = Query(14.9, ge=5.0, le=50.0),
    nd_ebit_max: float = Query(4.0, ge=1.0, le=10.0),
    int_cov_min: float = Query(3.0, ge=1.0, le=20.0),
    user: User = Depends(get_current_user),
):
    """月度滚动点时回测（PRD 第 8 节 E2 单调性 + 完整组合净值）。

    每月初按当时可见 ROCE 5Y + R1 杠杆 + PE 现算做 Q+R+V 判定，
    候选 = NearFairPrice，等权持有 1 月，输出净值 + CAGR/Sharpe/MaxDD。
    """
    if end <= start:
        raise HTTPException(400, "end 必须晚于 start")
    if (end - start).days < 30:
        raise HTTPException(400, "回测区间至少 30 天")
    try:
        report = monthly_rebalance(
            market=market, start=start, end=end,
            roce_threshold=roce_threshold, pe_max=pe_max,
            nd_ebit_max=nd_ebit_max, int_cov_min=int_cov_min,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return monthly_report_to_dict(report)
