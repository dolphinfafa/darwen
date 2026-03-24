# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Float, Date, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshot"

    score_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(32), ForeignKey("company.company_id"), index=True)
    asof_date: Mapped[date] = mapped_column(Date)
    model_version: Mapped[str] = mapped_column(String(30), comment="balanced|conservative|aggressive")
    survival: Mapped[float | None] = mapped_column(Float)
    replication: Mapped[float | None] = mapped_column(Float)
    adaptation: Mapped[float | None] = mapped_column(Float)
    moat: Mapped[float | None] = mapped_column(Float)
    valuation: Mapped[float | None] = mapped_column(Float)
    total: Mapped[float | None] = mapped_column(Float)
    tier: Mapped[str | None] = mapped_column(String(10), comment="Top|Watch|Reject")
    gating_flags: Mapped[str | None] = mapped_column(Text, comment="触发的红线标记 JSON")

    company: Mapped["Company"] = relationship(back_populates="score_snapshots")

    __table_args__ = (
        Index("ix_ss_company_date_model", "company_id", "asof_date", "model_version"),
    )
