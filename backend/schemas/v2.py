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
    roce_threshold: float = 0.20
    enable_ai_risk_layer: bool = False
    ai_provider: Optional[Literal["chatgpt", "minimax"]] = None

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
    config_snapshot: Optional[dict] = None
    error_msg: Optional[str] = None


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
    roce_series: list[dict] = []         # [{year, period_end, roce, capital_employed, ebit, ...}]
    leverage_series: list[dict] = []     # [{period_end, net_debt, net_debt_ebit, interest_coverage, current_ratio}]
    cash_quality_series: list[dict] = [] # [{period_end, cfo_ni_ratio, fcf}]
    dilution_series: list[dict] = []     # [{period_end, shares_outstanding}]
    valuation_snapshot: dict = {}        # {market_cap, pe_ttm, ev_ebit, enterprise_value, as_of}
    ai_result: Optional[RiskAIDetailOut] = None
    lineage: list[MetricLineageOut] = []


# ============ Backtest（M7 占位） ============

class BacktestCreateRequest(BaseModel):
    universe: Optional[str] = "us_default"
    start_date: date
    end_date: date
    rebalance_freq: Literal["monthly", "quarterly"] = "monthly"
    config: Optional[dict] = None
