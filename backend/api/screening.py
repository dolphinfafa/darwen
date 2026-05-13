# -*- coding: utf-8 -*-
"""V2 筛选 API：股票池 + 筛选执行 + 结果查询 + 单股详情。"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models.company import Company
from backend.models.metric_lineage_log import MetricLineageLog
from backend.models.metric_periodic import MetricPeriodic
from backend.models.risk_ai_result import RiskAIResult
from backend.models.screen_result import ScreenResult
from backend.models.screen_run import ScreenRun
from backend.models.security import Security
from backend.models.user import User
from backend.schemas.v2 import (
    CompanyDetailResponse,
    MetricLineageOut,
    RiskAIDetailOut,
    RiskAILabelOut,
    ScreenResultBucketResponse,
    ScreenResultRow,
    ScreenRunCreateRequest,
    ScreenRunCreateResponse,
    ScreenRunStatusResponse,
    UniversePreset,
)
from backend.screening.config import ScreenConfig
from backend.screening.funnel import _evaluate_one_company
from backend.screening.reason_labels import all_labels, lookup
from backend.services.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["screening"])


_STATUS_BUCKETS = ("Rejected", "Review", "TooExpensive", "NearFairPrice", "HighConviction")


# ---------------- Reason code 中文 label ----------------

@router.get("/reason-codes/labels")
def get_reason_code_labels():
    """返回全部 reason_code → {label, desc, layer, severity} 映射。

    前端启动时拉一次缓存即可，无鉴权（公开词典数据）。
    """
    return all_labels()


@router.get("/reason-codes/lookup/{code}")
def lookup_reason_code(code: str):
    """单个 reason_code 查询（含 _HIGH 后缀解析）。"""
    return lookup(code)


# ---------------- Universe ----------------

@router.get("/universe/presets", response_model=list[UniversePreset])
def list_presets(db: Session = Depends(get_db)):
    """返回预设股票池清单。"""
    us_count = db.scalar(select(func.count(Company.company_id)).where(Company.market == "US")) or 0
    cn_count = db.scalar(select(func.count(Company.company_id)).where(Company.market == "CN_A")) or 0
    return [
        UniversePreset(name="us_default", label="美股全量池", market="US", member_count=us_count),
        UniversePreset(name="cn_default", label="A 股蓝筹池", market="CN_A", member_count=cn_count),
        UniversePreset(name="all", label="混合全量", market="MIXED", member_count=us_count + cn_count),
    ]


def _resolve_universe(
    db: Session,
    preset: Optional[str],
    company_ids: Optional[list[str]],
) -> tuple[list[str], str]:
    """返回 (company_ids, market)。"""
    if company_ids:
        # 自定义池：从 DB 验证存在性，并按市场推断
        rows = db.execute(
            select(Company.company_id, Company.market).where(Company.company_id.in_(company_ids))
        ).all()
        if not rows:
            raise HTTPException(400, "company_ids 全部不存在")
        markets = {m for _, m in rows}
        market = next(iter(markets)) if len(markets) == 1 else "MIXED"
        return [c for c, _ in rows], market

    if preset == "us_default":
        rows = db.execute(select(Company.company_id).where(Company.market == "US")).all()
        return [r[0] for r in rows], "US"
    if preset == "cn_default":
        rows = db.execute(select(Company.company_id).where(Company.market == "CN_A")).all()
        return [r[0] for r in rows], "CN_A"
    if preset == "all":
        rows = db.execute(select(Company.company_id)).all()
        return [r[0] for r in rows], "MIXED"

    raise HTTPException(400, "必须提供 company_ids 或 preset")


# ---------------- ScreenRun ----------------

@router.post("/screen-run", response_model=ScreenRunCreateResponse)
def create_screen_run(
    body: ScreenRunCreateRequest,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启动一次筛选（异步）。立即返回 run_id；进度通过 GET /v2/screen-run/{id} 轮询。"""
    company_ids, market = _resolve_universe(db, body.preset, body.company_ids)
    if not company_ids:
        raise HTTPException(400, "universe 为空")

    config = ScreenConfig(
        roce_threshold=body.roce_threshold,
        risk_sensitivity=body.risk_sensitivity,
        valuation_mode=body.valuation_mode,
        ai_provider=body.ai_provider,
        enable_ai_risk_layer=body.enable_ai_risk_layer,
    )
    from dataclasses import asdict
    config_snapshot = asdict(config)

    run = ScreenRun(
        user_id=user.id,
        universe_name=body.universe_name or body.preset or "custom",
        universe_snapshot=company_ids,
        market=market,
        as_of_date=body.as_of_date,
        config_snapshot=config_snapshot,
        status="running",
        total_count=len(company_ids),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 后台异步执行
    bg.add_task(
        _execute_run_async,
        run.run_id, company_ids, config, body.as_of_date, user.id,
    )

    return ScreenRunCreateResponse(run_id=run.run_id, status=run.status, total=len(company_ids))


def _execute_run_async(
    run_id: int,
    company_ids: list[str],
    config: ScreenConfig,
    as_of_date: date,
    user_id: int,
) -> None:
    """后台任务：跑漏斗并更新 screen_run + screen_result。"""
    from datetime import datetime
    db = SessionLocal()
    try:
        passed = rejected = review = errors = 0
        for cid in company_ids:
            company = db.get(Company, cid)
            if company is None:
                continue
            try:
                params = _evaluate_one_company(
                    db, company, as_of_date, config,
                    user_id=user_id, run_id=run_id,
                )
                row = ScreenResult(run_id=run_id, **params)
                db.add(row)
                if params["status"] == "Rejected":
                    rejected += 1
                elif params["status"] == "Review":
                    review += 1
                else:
                    passed += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors += 1
                log.exception("screening failed for %s: %s", cid, e)
        db.commit()

        run = db.get(ScreenRun, run_id)
        run.status = "completed" if errors == 0 else "failed"
        run.finished_at = datetime.now()
        run.passed_count = passed
        run.rejected_count = rejected
        run.review_count = review
        run.error_msg = f"{errors} errors" if errors else None
        db.commit()
    finally:
        db.close()


@router.get("/screen-run/{run_id}", response_model=ScreenRunStatusResponse)
def get_screen_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")
    return ScreenRunStatusResponse(
        run_id=run.run_id,
        universe_name=run.universe_name,
        market=run.market,
        as_of_date=run.as_of_date,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_count=run.total_count,
        passed_count=run.passed_count,
        rejected_count=run.rejected_count,
        review_count=run.review_count,
        config_snapshot=run.config_snapshot,
        error_msg=run.error_msg,
    )


@router.get("/screen-run/{run_id}/results", response_model=ScreenResultBucketResponse)
def get_screen_results(
    run_id: int,
    per_bucket_limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """5 状态分桶 + 每桶前 N 条。"""
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")

    counts: dict[str, int] = {b: 0 for b in _STATUS_BUCKETS}
    rows: dict[str, list[ScreenResultRow]] = {b: [] for b in _STATUS_BUCKETS}

    q = (
        select(ScreenResult, Company, Security)
        .join(Company, ScreenResult.company_id == Company.company_id)
        .join(Security, Security.company_id == Company.company_id, isouter=True)
        .where(ScreenResult.run_id == run_id)
    )
    seen_companies: set[str] = set()
    for sr, c, sec in db.execute(q).all():
        if sr.company_id in seen_companies:
            continue
        seen_companies.add(sr.company_id)
        counts[sr.status] = counts.get(sr.status, 0) + 1
        if len(rows[sr.status]) < per_bucket_limit:
            rows[sr.status].append(
                ScreenResultRow(
                    company_id=sr.company_id,
                    ticker=sec.ticker if sec else None,
                    name=c.name,
                    market=c.market,
                    industry_name=c.industry_name,
                    status=sr.status,
                    q_passed=sr.q_passed,
                    q_strong_track=sr.q_strong_track,
                    r_action=sr.r_action,
                    v_state=sr.v_state,
                    reason_codes=sr.reason_codes or [],
                    metrics_snapshot=sr.metrics_snapshot or {},
                    ai_result_id=sr.ai_result_id,
                )
            )

    return ScreenResultBucketResponse(run_id=run_id, counts=counts, rows=rows)


# ---------------- 单股详情 ----------------

def _series_for(
    db: Session,
    company_id: str,
    formula_version: str,
    metric_names: tuple[str, ...],
    asof: date,
) -> list[dict]:
    """按 period_end 聚合多个 metric_name 为时序行。"""
    rows = db.execute(
        select(
            MetricPeriodic.period_end,
            MetricPeriodic.metric_name,
            MetricPeriodic.value,
            MetricPeriodic.notes,
        )
        .where(
            (MetricPeriodic.company_id == company_id)
            & (MetricPeriodic.formula_version == formula_version)
            & (MetricPeriodic.metric_name.in_(metric_names))
            & (MetricPeriodic.period_end <= asof)
        )
        .order_by(MetricPeriodic.period_end)
    ).all()
    by_date: dict[date, dict] = {}
    for r in rows:
        d = by_date.setdefault(r.period_end, {"period_end": r.period_end})
        d[r.metric_name] = float(r.value) if r.value is not None else None
        if r.notes and "notes" not in d:
            d["notes"] = r.notes
    return list(by_date.values())


@router.get("/screen-run/{run_id}/result/{company_id}", response_model=CompanyDetailResponse)
def get_company_detail(
    run_id: int,
    company_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")

    sr = db.execute(
        select(ScreenResult).where(
            (ScreenResult.run_id == run_id) & (ScreenResult.company_id == company_id)
        ).limit(1)
    ).scalar()
    if sr is None:
        raise HTTPException(404, "company not in this run")

    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    ticker = db.scalar(select(Security.ticker).where(Security.company_id == company_id))

    asof = run.as_of_date
    roce_series = _series_for(
        db, company_id, "roce_v1",
        ("roce", "ebit", "capital_employed", "nwc_ex_cash", "net_ppe",
         "operating_current_assets", "operating_current_liabilities"),
        asof,
    )
    leverage_series = _series_for(
        db, company_id, "leverage_v1",
        ("net_debt", "net_debt_ebit", "interest_coverage", "current_ratio"),
        asof,
    )
    cq_series = _series_for(
        db, company_id, "cash_quality_v1",
        ("cfo_ni_ratio", "fcf"),
        asof,
    )
    dil_series = _series_for(
        db, company_id, "dilution_v1",
        ("shares_outstanding",),
        asof,
    )
    val_rows = db.execute(
        select(MetricPeriodic.period_end, MetricPeriodic.metric_name, MetricPeriodic.value)
        .where(
            (MetricPeriodic.company_id == company_id)
            & (MetricPeriodic.formula_version == "valuation_v1")
            & (MetricPeriodic.period_end <= asof)
        )
        .order_by(MetricPeriodic.period_end.desc())
    ).all()
    val_snap: dict = {}
    if val_rows:
        latest_date = val_rows[0].period_end
        val_snap["as_of"] = latest_date.isoformat()
        for r in val_rows:
            if r.period_end == latest_date:
                val_snap[r.metric_name] = float(r.value) if r.value is not None else None

    # AI 结果
    ai_out: Optional[RiskAIDetailOut] = None
    if sr.ai_result_id:
        ai = db.get(RiskAIResult, sr.ai_result_id)
        if ai is not None:
            ai_out = RiskAIDetailOut(
                result_id=ai.result_id,
                asof_date=ai.asof_date,
                ai_provider=ai.ai_provider,
                model_name=ai.model_name,
                prompt_version=ai.prompt_version,
                overall_action=ai.overall_action,
                labels=[RiskAILabelOut(**lbl) for lbl in (ai.labels or [])],
                summary_cn=ai.summary_cn,
                latency_ms=ai.latency_ms,
                error_msg=ai.error_msg,
            )

    # 血缘
    lineage_rows = db.execute(
        select(MetricLineageLog)
        .where(MetricLineageLog.company_id == company_id)
        .order_by(MetricLineageLog.period_end.desc(), MetricLineageLog.field_name)
        .limit(200)
    ).scalars().all()
    lineage_out = [
        MetricLineageOut(
            field_name=r.field_name,
            source_code=r.source_code,
            source_record_key=r.source_record_key,
            period_end=r.period_end,
            effective_date=r.effective_date,
            raw_value=r.raw_value,
            formula_version=r.formula_version,
        )
        for r in lineage_rows
    ]

    return CompanyDetailResponse(
        company_id=company.company_id,
        name=company.name,
        market=company.market,
        industry_name=company.industry_name,
        ticker=ticker,
        cik=company.cik,
        list_date=company.list_date,
        instrument_type=company.instrument_type,
        result=ScreenResultRow(
            company_id=sr.company_id,
            ticker=ticker,
            name=company.name,
            market=company.market,
            industry_name=company.industry_name,
            status=sr.status,
            q_passed=sr.q_passed,
            q_strong_track=sr.q_strong_track,
            r_action=sr.r_action,
            v_state=sr.v_state,
            reason_codes=sr.reason_codes or [],
            metrics_snapshot=sr.metrics_snapshot or {},
            ai_result_id=sr.ai_result_id,
        ),
        roce_series=roce_series,
        leverage_series=leverage_series,
        cash_quality_series=cq_series,
        dilution_series=dil_series,
        valuation_snapshot=val_snap,
        ai_result=ai_out,
        lineage=lineage_out,
    )
