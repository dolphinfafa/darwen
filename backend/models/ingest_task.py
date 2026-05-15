# -*- coding: utf-8 -*-
"""手动 ingest 任务跟踪表（用户输入 CIK / 股票代码触发的拉数据任务）。"""
from datetime import datetime

from sqlalchemy import String, DateTime, Enum, Integer, BigInteger, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class IngestTask(Base):
    __tablename__ = "ingest_task"

    task_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), index=True
    )
    market: Mapped[str] = mapped_column(
        Enum("US", "CN_A", name="ingest_market_enum")
    )
    code: Mapped[str] = mapped_column(
        String(20), comment="CIK (美股) 或 6 位 stock_code (A股)"
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", name="ingest_task_status_enum"),
        default="pending",
    )
    current_stage: Mapped[str | None] = mapped_column(
        String(100), comment="fetching_company / ingest_income / compute_metrics 等"
    )
    company_id: Mapped[str | None] = mapped_column(
        String(32), comment="完成后填入"
    )
    error_msg: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
