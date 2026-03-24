# -*- coding: utf-8 -*-
from datetime import date
from pydantic import BaseModel


class CompanyBrief(BaseModel):
    company_id: str
    market: str
    name: str
    name_en: str | None = None
    industry_name: str | None = None
    ticker: str | None = None

    class Config:
        from_attributes = True


class ScoreResponse(BaseModel):
    company_id: str
    name: str
    market: str
    asof_date: date
    model_version: str
    survival: float | None
    replication: float | None
    adaptation: float | None
    moat: float | None
    valuation: float | None
    total: float | None
    tier: str | None
    gating_flags: str | None = None

    class Config:
        from_attributes = True


class FactorDetail(BaseModel):
    factor_code: str
    raw_value: float | None
    score: float | None
    lineage: str | None = None


class CompanyScoreDetail(BaseModel):
    company: CompanyBrief
    score: ScoreResponse
    factors: list[FactorDetail]


class ScreenerParams(BaseModel):
    market: str | None = None
    industry: str | None = None
    tier: str | None = None
    model: str = "balanced"
    asof: date | None = None
    sort_by: str = "total"
    sort_desc: bool = True
    limit: int = 200
    offset: int = 0
