# -*- coding: utf-8 -*-
"""筛选任务主表"""
from datetime import date, datetime

from sqlalchemy import String, DateTime, Date, ForeignKey, Integer, BigInteger, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import JSON

from backend.database import Base


class ScreenRun(Base):
    __tablename__ = "screen_run"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), index=True
    )
    universe_name: Mapped[str | None] = mapped_column(
        String(100), comment="股票池名称（us_default|cn_default|custom_xxx）"
    )
    universe_snapshot: Mapped[dict | None] = mapped_column(
        JSON, comment="股票池成员快照 [company_id, ...]"
    )
    market: Mapped[str] = mapped_column(
        Enum("US", "CN_A", "MIXED", name="run_market_enum")
    )
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    config_snapshot: Mapped[dict | None] = mapped_column(
        JSON, comment="阈值/敏感度/估值模式快照"
    )

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        Enum("running", "completed", "failed", "cancelled", name="run_status_enum"),
        default="running",
    )

    total_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text)
