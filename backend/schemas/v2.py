# -*- coding: utf-8 -*-
"""V2 API Pydantic schemas（三层漏斗 + 估值 + AI 风险层）。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============ User Settings ============

class APIKeyBindRequest(BaseModel):
    provider: Literal["chatgpt", "minimax"]
    api_key: str = Field(min_length=8, max_length=512)
    group_id: Optional[str] = None  # MiniMax 需要

    model_config = {"extra": "ignore"}


class APIKeyStatusResponse(BaseModel):
    chatgpt_bound: bool
    chatgpt_masked: Optional[str] = None
    minimax_bound: bool
    minimax_masked: Optional[str] = None
    minimax_group_id: Optional[str] = None
    default_provider: str


class APIKeyDeleteRequest(BaseModel):
    provider: Literal["chatgpt", "minimax"]


class DefaultProviderUpdateRequest(BaseModel):
    provider: Literal["chatgpt", "minimax"]


# ============ Universe / Screening ============

class UniversePreset(BaseModel):
    """预设股票池信息。"""
    name: str          # us_default / cn_default / sp500_etc
    label: str         # 中文展示名
    market: str        # US / CN_A / MIXED
    member_count: int


class ScreenRunCreateRequest(BaseModel):
    """启动一次筛选。"""
    universe_name: Optional[str] = "custom"
    company_ids: Optional[list[str]] = None     # 显式公司列表（与 preset 二选一）
    preset: Optional[str] = None                # us_default / cn_default
    as_of_date: date = Field(default_factory=lambda: date(2024, 12, 31))

    # 配置（透传到 ScreenConfig）
    risk_sensitivity: Literal["strict", "standard", "loose"] = "standard"
    valuation_mode: Literal["strict", "standard", "loose"] = "strict"
    roce_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    roce_lookback_years: int = Field(default=5, ge=3, le=15)
    enable_ai_risk_layer: bool = False
    ai_mode: Literal["off", "key_stage", "full"] = "off"  # AI 介入范围：不启用/仅风险层/全程
    ai_provider: Optional[Literal["chatgpt", "minimax"]] = None
    auto_advance: bool = False  # True=三层连跑；False=每层暂停等人工 gate

    model_config = {"extra": "ignore"}


class ScreenRunCreateResponse(BaseModel):
    run_id: int
    status: str
    total: int


class ScreenRunStatusResponse(BaseModel):
    run_id: int
    universe_name: Optional[str]
    market: str
    as_of_date: date
    status: str           # running / completed / failed / cancelled
    started_at: datetime
    finished_at: Optional[datetime]
    total_count: int
    passed_count: int
    rejected_count: int
    review_count: int
    progress_count: int = 0
    current_company_name: Optional[str] = None
    config_snapshot: Optional[dict] = None
    error_msg: Optional[str] = None
    # 三层漏斗分层状态（funnel_v2）
    current_layer: Optional[str] = None   # roce|sturdiness|risk|done
    layer_status: Optional[str] = None    # running|awaiting_review|completed|failed
    auto_advance: bool = False


class ScreenRunSummary(BaseModel):
    """精简版用于"我的筛选历史"列表。"""
    run_id: int
    universe_name: Optional[str]
    market: str
    as_of_date: date
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_count: int
    progress_count: int = 0
    passed_count: int
    rejected_count: int
    review_count: int
    current_company_name: Optional[str] = None


class ScreenResultRow(BaseModel):
    company_id: str
    ticker: Optional[str] = None
    name: str
    market: str
    industry_name: Optional[str] = None
    status: str
    q_passed: bool
    q_strong_track: bool
    r_action: Optional[str]
    v_state: Optional[str]
    reason_codes: list[str] = []
    metrics_snapshot: dict[str, Any] = {}
    ai_result_id: Optional[int] = None


class ScreenResultBucketResponse(BaseModel):
    """5 状态分桶 + 计数。"""
    run_id: int
    counts: dict[str, int]   # {Rejected: N, Review: M, ...}
    rows: dict[str, list[ScreenResultRow]]  # 每桶的列表（可分页限制）


# ============ Single-stock detail ============

class RiskAILabelOut(BaseModel):
    label: str
    severity: str
    confidence: float
    evidence_doc_ids: list[str] = []
    short_reason: str = ""


class RiskAIDetailOut(BaseModel):
    result_id: int
    asof_date: date
    ai_provider: str
    model_name: str
    prompt_version: str
    overall_action: str
    labels: list[RiskAILabelOut] = []
    summary_cn: Optional[str] = None
    latency_ms: Optional[int] = None
    error_msg: Optional[str] = None


class MetricLineageOut(BaseModel):
    field_name: str
    source_code: Optional[str]
    source_record_key: Optional[str]
    period_end: Optional[date]
    effective_date: Optional[date]
    raw_value: Optional[float]
    formula_version: Optional[str]


class CompanyDetailResponse(BaseModel):
    """单股详情：基础 + Q 层 + R 层 + V 层 + AI + 血缘 + ROCE 时序。"""
    company_id: str
    name: str
    market: str
    industry_name: Optional[str] = None
    ticker: Optional[str] = None
    cik: Optional[str] = None
    list_date: Optional[date] = None
    instrument_type: str

    result: ScreenResultRow
    rejected_at_layer: Optional[str] = None   # roce|sturdiness|risk；空=入选
    layer_results: dict = {}                  # funnel_v2 逐层结果（含 AI principles + evidence）
    roce_series: list[dict] = []         # [{year, period_end, roce, capital_employed, ebit, ...}]
    leverage_series: list[dict] = []     # [{period_end, net_debt, net_debt_ebit, interest_coverage, current_ratio}]
    cash_quality_series: list[dict] = [] # [{period_end, cfo_ni_ratio, fcf}]
    dilution_series: list[dict] = []     # [{period_end, shares_outstanding}]
    valuation_snapshot: dict = {}        # {market_cap, pe_ttm, ev_ebit, enterprise_value, as_of}
    ai_result: Optional[RiskAIDetailOut] = None
    lineage: list[MetricLineageOut] = []


# ============ 我的股票池 watchlist ============

class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WatchlistRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WatchlistItemAddRequest(BaseModel):
    company_id: str
    source_run_id: Optional[int] = None
    note: Optional[str] = None


class AddToWatchlistRequest(BaseModel):
    """详情页"进入我的股票池"：指定已有池 id，或给名字自动建/复用。"""
    company_id: str
    watchlist_id: Optional[int] = None
    watchlist_name: Optional[str] = None
    source_run_id: Optional[int] = None
    note: Optional[str] = None


class WatchlistSummary(BaseModel):
    id: int
    name: str
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistItemOut(BaseModel):
    company_id: str
    ticker: Optional[str] = None
    name: str
    market: str
    industry_name: Optional[str] = None
    note: Optional[str] = None
    source_run_id: Optional[int] = None
    added_at: datetime


class WatchlistDetailResponse(BaseModel):
    id: int
    name: str
    items: list[WatchlistItemOut] = []


# ============ 三层漏斗（funnel_v2）============

class ManualActionRequest(BaseModel):
    """人工 gate：放行被过滤的 / 剔除已通过的（针对当前层）。"""
    company_id: str
    action: Literal["force_pass", "force_reject"]
    note: Optional[str] = None


class FunnelCompany(BaseModel):
    company_id: str
    ticker: Optional[str] = None
    name: str
    market: str
    industry_name: Optional[str] = None
    reason_codes: list[str] = []
    metrics_snapshot: dict[str, Any] = {}
    layer_results: dict[str, Any] = {}
    manual_action: Optional[dict] = None


class FunnelLayer(BaseModel):
    layer: str            # roce | sturdiness | risk
    label: str
    state: str            # pending | running | awaiting_review | completed
    input_count: int      # 进入本层的公司数
    passed_count: int     # 通过本层（进入下一层）
    rejected_count: int   # 本层被过滤
    rejected: list[FunnelCompany] = []   # 被本层过滤的公司（含人工剔除）


class FunnelResponse(BaseModel):
    run_id: int
    run_status: str               # running | completed | failed
    current_layer: Optional[str]
    layer_status: Optional[str]
    auto_advance: bool
    total: int
    layers: list[FunnelLayer]
    survivors: list[FunnelCompany] = []  # 当前存活/最终入选（rejected_at_layer 为空）


class AdvanceResponse(BaseModel):
    run_id: int
    next_layer: Optional[str]
    layer_status: str


class RunRenameRequest(BaseModel):
    """重命名筛选批次（我的筛选历史页）。"""
    name: str = Field(min_length=1, max_length=100)


class EvidenceDoc(BaseModel):
    """AI 原因出处文档（evidence_doc_ids 解析）。"""
    doc_id: str
    title: str = ""
    source_type: Optional[str] = None
    doc_type: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None


# ============ Backtest（M7 占位） ============

class BacktestCreateRequest(BaseModel):
    universe: Optional[str] = "us_default"
    start_date: date
    end_date: date
    rebalance_freq: Literal["monthly", "quarterly"] = "monthly"
    config: Optional[dict] = None


# ============ Company List / Ingest / Profile ============

class CompanyListItem(BaseModel):
    """股票池选股表格行。"""
    company_id: str
    market: str
    ticker: Optional[str] = None
    name: str
    industry_name: Optional[str] = None
    instrument_type: str
    fiscal_year_end_month: Optional[int] = None


class IndustryItem(BaseModel):
    industry_name: str
    count: int


class CompanyIngestRequest(BaseModel):
    market: Literal["US", "CN_A"]
    code: str = Field(min_length=1, max_length=20, description="美股 CIK 或 A 股 6 位代码")


class CompanyIngestStatusResponse(BaseModel):
    task_id: int
    market: str
    code: str
    status: str            # pending / running / completed / failed
    current_stage: Optional[str] = None
    company_id: Optional[str] = None
    error_msg: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class ProfilePoint(BaseModel):
    """单条公司画像观点（带数据依据）。"""
    category: Literal["strength", "concern", "neutral"]
    title: str
    desc: str
    metric: Optional[str] = None
    value: Optional[str] = None
    period: Optional[str] = None


class CompanyProfileResponse(BaseModel):
    company_id: str
    name: str
    market: str
    industry_name: Optional[str] = None
    instrument_type: str
    business_summary: str
    strengths: list[ProfilePoint] = []
    concerns: list[ProfilePoint] = []
    neutral: list[ProfilePoint] = []
