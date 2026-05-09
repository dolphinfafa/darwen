# -*- coding: utf-8 -*-
"""预计算的点时指标表（ROCE/EBIT/CapEmployed/NetDebt/...）"""
from datetime import date, datetime

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Index, BigInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import JSON

from backend.database import Base


class MetricPeriodic(Base):
    __tablename__ = "metric_periodic"

    metric_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    period_end: Mapped[date] = mapped_column(Date, index=True)
    metric_name: Mapped[str] = mapped_column(
        String(60),
        comment="roce|capital_employed|ebit|fcf|net_debt|interest_coverage|cfo_ni_ratio|share_count|...",
    )
    value: Mapped[float | None] = mapped_column(Float)
    formula_version: Mapped[str] = mapped_column(String(20), default="v1")
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    source_fact_ids: Mapped[list | None] = mapped_column(
        JSON, comment="血缘：用了哪些 fact_id 计算得来"
    )
    notes: Mapped[str | None] = mapped_column(
        String(200), comment="如 NEGATIVE_CAPITAL_EMPLOYED 等标签"
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_end", "metric_name", "formula_version",
            name="uq_metric_periodic",
        ),
        Index("ix_metric_periodic_company_metric", "company_id", "metric_name"),
    )
