# -*- coding: utf-8 -*-
"""字段血缘日志（按 PRD 第 7 节强制要求）"""
from datetime import date, datetime

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Index, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MetricLineageLog(Base):
    __tablename__ = "metric_lineage_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("screen_run.run_id"), index=True
    )
    company_id: Mapped[str] = mapped_column(String(32), index=True)
    field_name: Mapped[str] = mapped_column(String(80))
    source_code: Mapped[str | None] = mapped_column(
        String(20), comment="PG-FS|SEC|TS-FS|CNINFO|EXCH|WIND|IFIND|NDL|PG-NEWS"
    )
    source_record_key: Mapped[str | None] = mapped_column(
        String(200), comment="源记录主键（fact_id|filing_id|doc_id 等）"
    )
    period_end: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    raw_value: Mapped[float | None] = mapped_column(Float)
    normalized_value: Mapped[float | None] = mapped_column(Float)
    formula_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_lineage_run_company", "run_id", "company_id"),
        Index("ix_lineage_company_field", "company_id", "field_name"),
    )
