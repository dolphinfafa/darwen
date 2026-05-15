# -*- coding: utf-8 -*-
"""手动新增股票 ingest API（优化2）。

POST /v2/companies/ingest    {market, code} → 创建 IngestTask + 后台执行
GET  /v2/companies/ingest/{task_id}    查询进度
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models.company import Company
from backend.models.ingest_task import IngestTask
from backend.models.user import User
from backend.schemas.v2 import (
    CompanyIngestRequest,
    CompanyIngestStatusResponse,
)
from backend.services.auth import get_current_user


log = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/companies", tags=["companies"])


def _normalize_us_cik(code: str) -> Optional[str]:
    """美股 CIK 标准化：去前导零 + 数字校验。返回原始数字（不补 0）供 ingest_company 用。"""
    s = code.strip().lstrip("0").strip()
    if not s or not s.isdigit():
        return None
    return s


def _normalize_cn_code(code: str) -> Optional[str]:
    """A 股 6 位代码校验。"""
    s = code.strip()
    if re.fullmatch(r"\d{6}", s):
        return s
    return None


@router.post("/ingest", response_model=CompanyIngestStatusResponse)
def ingest_company_endpoint(
    body: CompanyIngestRequest,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """触发新公司 ingest。同步校验 + 异步执行。"""
    if body.market == "US":
        norm = _normalize_us_cik(body.code)
        if norm is None:
            raise HTTPException(400, "CIK 必须是数字（可带前导零）")
        # 检查是否已存在
        existing = db.scalar(
            select(Company.company_id).where(Company.cik == norm.zfill(10))
        )
        if existing:
            raise HTTPException(409, f"该公司已在系统：{existing}")
    else:  # CN_A
        norm = _normalize_cn_code(body.code)
        if norm is None:
            raise HTTPException(400, "A 股代码必须是 6 位数字")
        existing = db.scalar(
            select(Company.company_id).where(Company.stock_code == norm)
        )
        if existing:
            raise HTTPException(409, f"该公司已在系统：{existing}")

    task = IngestTask(
        user_id=user.id, market=body.market, code=norm,
        status="pending", current_stage="queued",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    bg.add_task(_execute_ingest, task.task_id, body.market, norm)

    return _to_status(task)


@router.get("/ingest/{task_id}", response_model=CompanyIngestStatusResponse)
def get_ingest_status(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    if task.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your task")
    return _to_status(task)


def _to_status(task: IngestTask) -> CompanyIngestStatusResponse:
    return CompanyIngestStatusResponse(
        task_id=task.task_id,
        market=task.market,
        code=task.code,
        status=task.status,
        current_stage=task.current_stage,
        company_id=task.company_id,
        error_msg=task.error_msg,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _update_stage(db: Session, task_id: int, stage: str, status: str = "running") -> None:
    """独立 UPDATE 刷新阶段，立即 commit。"""
    from sqlalchemy import update as sa_update
    db.execute(
        sa_update(IngestTask).where(IngestTask.task_id == task_id).values(
            current_stage=stage, status=status,
        )
    )
    db.commit()


def _finish(db: Session, task_id: int, *, status: str, company_id: Optional[str] = None,
            error_msg: Optional[str] = None) -> None:
    from sqlalchemy import update as sa_update
    db.execute(
        sa_update(IngestTask).where(IngestTask.task_id == task_id).values(
            status=status, company_id=company_id, error_msg=error_msg,
            finished_at=datetime.now(), current_stage="done" if status == "completed" else "failed",
        )
    )
    db.commit()


def _execute_ingest(task_id: int, market: str, code: str) -> None:
    """后台执行：调对应 pipeline + 跑 metric_periodic。"""
    db = SessionLocal()
    try:
        try:
            if market == "US":
                _ingest_us(db, task_id, code)
            else:
                _ingest_cn(db, task_id, code)
        except Exception as e:  # noqa: BLE001
            log.exception("ingest task %d failed", task_id)
            _finish(db, task_id, status="failed", error_msg=str(e)[:1000])
    finally:
        db.close()


def _ingest_us(db: Session, task_id: int, cik: str) -> None:
    from backend.pipeline.sec_edgar.runner import ingest_company as sec_ingest
    from backend.pipeline.sec_edgar.submissions import _make_company_id
    from backend.pipeline.sec_edgar.fill_fiscal_year_end import _parse_mmdd_month, fetch_submission
    from backend.metrics.compute import persist_all_metrics_for_company

    _update_stage(db, task_id, "fetching_sec_company")
    ok = sec_ingest(db, cik)
    if not ok:
        _finish(db, task_id, status="failed", error_msg="SEC ingest_company 返回 False")
        return

    company_id = _make_company_id(cik)

    # 填 fiscal_year_end_month（取自 submissions.fiscalYearEnd）
    _update_stage(db, task_id, "fetching_fiscal_year_end")
    try:
        data = fetch_submission(cik)
        if data:
            m = _parse_mmdd_month(data.get("fiscalYearEnd", ""))
            if m is not None:
                from sqlalchemy import update as sa_update
                db.execute(
                    sa_update(Company).where(Company.company_id == company_id).values(
                        fiscal_year_end_month=m
                    )
                )
                db.commit()
    except Exception:  # noqa: BLE001
        log.exception("fye fill failed for %s", company_id)

    _update_stage(db, task_id, "computing_metrics")
    persist_all_metrics_for_company(db, company_id)

    _finish(db, task_id, status="completed", company_id=company_id)


def _ingest_cn(db: Session, task_id: int, stock_code: str) -> None:
    from backend.pipeline.cn_stock_v2.tushare_client import ingest_one_stock
    from backend.metrics.compute import persist_all_metrics_for_company

    _update_stage(db, task_id, "fetching_tushare_data")
    stats = ingest_one_stock(db, stock_code)
    if stats.get("status") != "ok":
        _finish(db, task_id, status="failed",
                error_msg=f"Tushare ingest 失败: {stats.get('error', 'unknown')}")
        return

    company_id = f"CN_{stock_code}"

    # 填 fiscal_year_end_month=12（A 股一律 12 月）
    from sqlalchemy import update as sa_update
    db.execute(
        sa_update(Company).where(Company.company_id == company_id).values(
            fiscal_year_end_month=12
        )
    )
    db.commit()

    _update_stage(db, task_id, "computing_metrics")
    persist_all_metrics_for_company(db, company_id)

    _finish(db, task_id, status="completed", company_id=company_id)
