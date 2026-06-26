# -*- coding: utf-8 -*-
"""V2 筛选 API：股票池 + 筛选执行 + 结果查询 + 单股详情。"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
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
    CompanyListItem,
    CompanyProfileResponse,
    FunnelCompany,
    FunnelLayer,
    FunnelResponse,
    IndustryItem,
    EvidenceDoc,
    MetricLineageOut,
    RunRenameRequest,
    RiskAIDetailOut,
    RiskAILabelOut,
    ScreenResultBucketResponse,
    ScreenResultRow,
    ScreenRunCreateRequest,
    ScreenRunCreateResponse,
    ScreenRunStatusResponse,
    ScreenRunSummary,
    UniversePreset,
)
from fastapi.responses import RedirectResponse
from backend.screening.config import ScreenConfig
from backend.screening import funnel_v2
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


# ---------------- 公司列表 + 行业（优化1）----------------

@router.get("/companies", response_model=list[CompanyListItem])
def list_companies(
    market: Optional[str] = Query(None, description="US | CN_A | 空（全部）"),
    industry: Optional[str] = Query(None, description="industry_name 精确匹配"),
    search: Optional[str] = Query(None, description="ticker / name / company_id 模糊"),
    limit: int = Query(5000, ge=1, le=10000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回过滤后的公司列表。供 UniverseConfig 表格选股使用。"""
    from sqlalchemy import or_
    q = select(Company, Security).join(
        Security, Security.company_id == Company.company_id, isouter=True,
    )
    conditions = []
    if market:
        conditions.append(Company.market == market)
    if industry:
        conditions.append(Company.industry_name == industry)
    if search:
        kw = f"%{search}%"
        conditions.append(
            or_(
                Company.name.like(kw),
                Security.ticker.like(kw),
                Company.company_id.like(kw),
                Company.stock_code.like(kw),
                Company.cik.like(kw),
            )
        )
    if conditions:
        q = q.where(*conditions)
    q = q.order_by(Company.market, Company.name).limit(limit)

    rows = db.execute(q).all()
    seen: set[str] = set()
    out: list[CompanyListItem] = []
    for c, sec in rows:
        if c.company_id in seen:
            continue
        seen.add(c.company_id)
        out.append(CompanyListItem(
            company_id=c.company_id,
            market=c.market,
            ticker=(sec.ticker if sec else (c.stock_code or c.cik)),
            name=c.name,
            industry_name=c.industry_name,
            instrument_type=c.instrument_type,
            fiscal_year_end_month=c.fiscal_year_end_month,
        ))
    return out


@router.get("/industries", response_model=list[IndustryItem])
def list_industries(
    market: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回去重后的 industry_name 列表（按公司数倒序），供前端 dropdown。"""
    from sqlalchemy import func as sa_func
    q = select(
        Company.industry_name,
        sa_func.count(Company.company_id).label("n"),
    ).where(Company.industry_name.isnot(None))
    if market:
        q = q.where(Company.market == market)
    q = q.group_by(Company.industry_name).order_by(sa_func.count(Company.company_id).desc())
    return [IndustryItem(industry_name=r[0], count=r[1]) for r in db.execute(q).all()]


# ---------------- 公司画像（优化3）----------------

@router.get("/company/{company_id}/profile", response_model=CompanyProfileResponse)
def get_company_profile(
    company_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """规则化生成公司画像（业务描述 + 优势/隐忧/中性观点 + 数据依据）。"""
    from backend.screening.company_profile import generate_profile
    profile = generate_profile(db, company_id)
    if profile is None:
        raise HTTPException(404, "company not found")
    return profile


# ---------------- 财报下载 302 跳转（优化4）----------------

@router.get("/market-news")
def list_market_news(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """市场资讯（Tushare major_news 大盘新闻）。进页面按需拉最近几天（url 去重）+ 返回最新 N 条。"""
    from backend.models.market_news import MarketNews
    try:
        from backend.pipeline.cn_stock_v2.tushare_client import ingest_market_news
        ingest_market_news(db, days=2)
    except Exception:  # noqa: BLE001  拉取失败不阻塞，返回库存
        pass
    rows = db.execute(
        select(MarketNews).order_by(MarketNews.published_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "title": r.title, "url": r.url, "source": r.source,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows
    ]


@router.get("/company/{company_id}/filing-url")
def get_filing_url(
    company_id: str,
    year: int = Query(..., description="财年年份"),
    form: str = Query("10-K", description="10-K / 10-Q / 8-K"),
    db: Session = Depends(get_db),
):
    """按 (company, year, form_type) 查 filing，302 redirect 到 SEC 原文链接。

    公开端点（不鉴权）：前端用 <a target=_blank> 直接打开，浏览器导航不带 Authorization；
    且仅重定向到 SEC 公开文件，无敏感数据。
    """
    from backend.models.filing import Filing
    from datetime import date as date_cls
    from sqlalchemy import and_

    # filing 表只有 filed_date（提交日），没有 period_end。10-K 通常在财年末后
    # 60-90 天内 filed，所以"FY{year}"的 10-K filed_date 应该在 {year}-01-01 至
    # {year+1}-04-30 之间（容忍各种财年末月份 + 披露延迟）
    window_start = date_cls(year, 1, 1)
    window_end = date_cls(year + 1, 4, 30)

    def _query(require_pdf: bool):
        conds = [
            Filing.company_id == company_id,
            Filing.form_type == form,
            Filing.filed_date >= window_start,
            Filing.filed_date <= window_end,
        ]
        if require_pdf:
            conds.append(Filing.url_pdf.isnot(None))
        return db.execute(
            select(Filing.url_pdf, Filing.url, Filing.filing_id, Filing.filed_date)
            .where(and_(*conds))
            .order_by(Filing.filed_date.desc())
            .limit(1)
        ).first()

    row = _query(require_pdf=True) or _query(require_pdf=False)
    if row is None:
        raise HTTPException(404, f"未找到 {company_id} 的 {year} {form} filing")
    target = row.url_pdf or row.url
    if not target:
        raise HTTPException(404, f"filing {row.filing_id} 缺失 url")
    return RedirectResponse(url=target, status_code=302)


# ---------------- AI 分析提示词（优化5）----------------

@router.get("/company/{company_id}/analysis-prompt")
def get_analysis_prompt(
    company_id: str,
    run_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成给 ChatGPT/Claude 用的中文分析 prompt（含 Pulak 方法论 + 指标 + 引导问题）。"""
    from backend.screening.analysis_prompt import generate_analysis_prompt
    prompt = generate_analysis_prompt(db, company_id, run_id=run_id)
    if prompt is None:
        raise HTTPException(404, "company not found")
    return {"company_id": company_id, "prompt": prompt}


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
        roce_lookback_years=body.roce_lookback_years,
        risk_sensitivity=body.risk_sensitivity,
        valuation_mode=body.valuation_mode,
        ai_provider=body.ai_provider,
        ai_mode=body.ai_mode,
        # 兼容：ai_mode 非 off 即视为启用 AI（旧 R 层引擎仍读此字段）
        enable_ai_risk_layer=body.enable_ai_risk_layer or body.ai_mode != "off",
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
        current_layer="roce",
        layer_status="running",
        auto_advance=body.auto_advance,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 后台执行：三层漏斗 v2 从 ROCE 层开始（auto_advance 决定是否连跑）
    bg.add_task(funnel_v2.start_run, run.run_id)

    return ScreenRunCreateResponse(run_id=run.run_id, status=run.status, total=len(company_ids))


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
        progress_count=run.progress_count,
        current_company_name=run.current_company_name,
        config_snapshot=run.config_snapshot,
        error_msg=run.error_msg,
        current_layer=run.current_layer,
        layer_status=run.layer_status,
        auto_advance=bool(run.auto_advance),
    )


@router.get("/my-runs", response_model=list[ScreenRunSummary])
def list_my_runs(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户所有 screen_run（按 started_at desc），供"我的筛选历史"页。"""
    rows = db.execute(
        select(ScreenRun)
        .where(ScreenRun.user_id == user.id)
        .order_by(ScreenRun.started_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        ScreenRunSummary(
            run_id=r.run_id,
            universe_name=r.universe_name,
            market=r.market,
            as_of_date=r.as_of_date,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            total_count=r.total_count,
            progress_count=r.progress_count,
            passed_count=r.passed_count,
            rejected_count=r.rejected_count,
            review_count=r.review_count,
            current_company_name=r.current_company_name,
        )
        for r in rows
    ]


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


# ---------------- 三层漏斗（funnel_v2）----------------

_LAYER_LABELS = {"roce": "ROCE 门槛", "sturdiness": "稳健性筛选", "risk": "风险性筛选"}
_LAYER_ORDER = ("roce", "sturdiness", "risk")


def _to_funnel_company(sr, name, market, industry_name, ticker) -> FunnelCompany:
    return FunnelCompany(
        company_id=sr.company_id,
        ticker=ticker,
        name=name,
        market=market,
        industry_name=industry_name,
        reason_codes=sr.reason_codes or [],
        metrics_snapshot=sr.metrics_snapshot or {},
        layer_results=sr.layer_results or {},
        manual_action=sr.manual_action,
    )


@router.get("/screen-run/{run_id}/funnel", response_model=FunnelResponse)
def get_funnel(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """三层漏斗视图：每层 in/out 计数 + 各层被过滤公司列表 + 当前存活/入选。"""
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")

    q = (
        select(ScreenResult, Company, Security)
        .join(Company, ScreenResult.company_id == Company.company_id)
        .join(Security, Security.company_id == Company.company_id, isouter=True)
        .where(ScreenResult.run_id == run_id)
        .order_by(ScreenResult.result_id)
    )
    seen: set[str] = set()
    rejected_by_layer: dict[str, list[FunnelCompany]] = {l: [] for l in _LAYER_ORDER}
    survivors: list[FunnelCompany] = []
    for sr, c, sec in db.execute(q).all():
        if sr.company_id in seen:
            continue
        seen.add(sr.company_id)
        fc = _to_funnel_company(sr, c.name, c.market, c.industry_name, sec.ticker if sec else None)
        if sr.rejected_at_layer in rejected_by_layer:
            rejected_by_layer[sr.rejected_at_layer].append(fc)
        elif sr.status in ("Rejected", "TooExpensive"):
            # 兼容旧引擎数据（无 rejected_at_layer 但 status 已排除）：归第一层，避免误判入选
            rejected_by_layer["roce"].append(fc)
        else:
            survivors.append(fc)

    # 按 ROCE（roce_median，回溯窗口中位）从高到低排序：入选与各层出局列表均如此，
    # ROCE 缺失（Q0 排除 / 负资本等）排末尾。
    def _roce_key(fc: FunnelCompany) -> float:
        v = (fc.metrics_snapshot or {}).get("roce_median")
        return v if isinstance(v, (int, float)) else float("-inf")

    survivors.sort(key=_roce_key, reverse=True)
    for _l in rejected_by_layer:
        rejected_by_layer[_l].sort(key=_roce_key, reverse=True)

    cur = run.current_layer or "roce"
    done = (cur == "done") or (run.status == "completed")
    cur_idx = _LAYER_ORDER.index(cur) if cur in _LAYER_ORDER else len(_LAYER_ORDER)

    layers: list[FunnelLayer] = []
    prev_input = run.total_count
    for i, l in enumerate(_LAYER_ORDER):
        rej = len(rejected_by_layer[l])
        passed = prev_input - rej
        if done or i < cur_idx:
            state = "completed"
        elif i == cur_idx:
            state = run.layer_status or "running"
        else:
            state = "pending"
        layers.append(FunnelLayer(
            layer=l, label=_LAYER_LABELS[l], state=state,
            input_count=prev_input, passed_count=passed, rejected_count=rej,
            rejected=rejected_by_layer[l],
        ))
        prev_input = passed

    return FunnelResponse(
        run_id=run_id,
        run_status=run.status,
        current_layer=run.current_layer,
        layer_status=run.layer_status,
        auto_advance=bool(run.auto_advance),
        total=run.total_count,
        layers=layers,
        survivors=survivors,
    )


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

    # 进详情页按需刷新最新行情（当天去重 + 容错；失败降级用库存值）
    from backend.services.quote import refresh_quote
    refresh_quote(db, company_id)

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
    # 估值用实时口径：刚按需刷新行情后，用 today 算最新价 + 真 TTM 市盈率（而非读历史预计算）
    from datetime import date as _date
    from backend.metrics.valuation import compute_valuation_snapshot
    _vs = compute_valuation_snapshot(db, company_id, _date.today(), market=company.market)
    val_snap: dict = {
        "as_of": _vs.as_of_date.isoformat(),
        "latest_close": _vs.latest_close,
        "latest_trade_date": _vs.latest_trade_date.isoformat() if _vs.latest_trade_date else None,
        "market_cap": _vs.market_cap,
        "pe_ttm": _vs.pe_ttm,
    }

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

    # A股财报逐年直链：anns_d 入库的年报公告(text_document doc_type=annual) 按财年 → 巨潮 url
    cn_filings: dict[str, str] = {}
    if company.market == "CN_A":
        import re as _re
        from backend.models.text_document import TextDocument
        for t, u in db.execute(
            select(TextDocument.title, TextDocument.content_url).where(
                TextDocument.company_id == company_id,
                TextDocument.source_type == "TS-ANN",
                TextDocument.doc_type == "annual",
                TextDocument.content_url.isnot(None),
            ).order_by(TextDocument.published_at.desc())
        ).all():
            m = _re.search(r"(\d{4})\s*年年度报告", t or "")
            if m and m.group(1) not in cn_filings:
                cn_filings[m.group(1)] = u

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
        rejected_at_layer=sr.rejected_at_layer,
        layer_results=sr.layer_results or {},
        roce_series=roce_series,
        leverage_series=leverage_series,
        cash_quality_series=cq_series,
        dilution_series=dil_series,
        valuation_snapshot=val_snap,
        cn_filings=cn_filings,
        ai_result=ai_out,
        lineage=lineage_out,
    )


@router.get("/company/{company_id}/evidence", response_model=list[EvidenceDoc])
def get_evidence(
    company_id: str,
    doc_ids: str = Query(..., description="逗号分隔的 doc_xxx（AI evidence_doc_ids）"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把 AI 原因的 evidence_doc_ids 解析为可读出处（标题 + 来源 + 链接）。"""
    from backend.models.text_document import TextDocument
    raw_ids = []
    for x in doc_ids.split(","):
        x = x.strip().replace("doc_", "")
        if x.isdigit():
            raw_ids.append(int(x))
    if not raw_ids:
        return []
    rows = db.execute(
        select(TextDocument).where(
            TextDocument.doc_id.in_(raw_ids),
            TextDocument.company_id == company_id,
        )
    ).scalars().all()
    return [
        EvidenceDoc(
            doc_id=f"doc_{d.doc_id}", title=d.title or "",
            source_type=d.source_type, doc_type=d.doc_type, url=d.content_url,
            published_at=d.published_at.isoformat() if d.published_at else None,
        )
        for d in rows
    ]


@router.patch("/my-runs/{run_id}", response_model=ScreenRunSummary)
def rename_run(
    run_id: int,
    body: RunRenameRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重命名筛选批次（universe_name）。仅本人可改。"""
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")
    run.universe_name = body.name.strip()
    db.add(run)
    db.commit()
    db.refresh(run)
    return ScreenRunSummary(
        run_id=run.run_id, universe_name=run.universe_name, market=run.market,
        as_of_date=run.as_of_date, status=run.status, started_at=run.started_at,
        finished_at=run.finished_at, total_count=run.total_count,
        progress_count=run.progress_count, passed_count=run.passed_count,
        rejected_count=run.rejected_count, review_count=run.review_count,
        current_company_name=run.current_company_name,
    )


@router.delete("/my-runs/{run_id}", status_code=204)
def delete_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除筛选批次及其全部子结果。仅本人（或管理员）可删。

    子表按外键依赖顺序清理：screen_result（引用 run_id 与 risk_ai_result）→
    risk_ai_result → metric_lineage_log → screen_run。
    """
    run = db.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your run")

    db.execute(delete(ScreenResult).where(ScreenResult.run_id == run_id))
    db.execute(delete(RiskAIResult).where(RiskAIResult.run_id == run_id))
    db.execute(delete(MetricLineageLog).where(MetricLineageLog.run_id == run_id))
    db.execute(delete(ScreenRun).where(ScreenRun.run_id == run_id))
    db.commit()
    return None
