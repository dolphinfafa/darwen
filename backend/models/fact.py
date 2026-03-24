# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Float, Date, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Fact(Base):
    __tablename__ = "fact"

    fact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(32), ForeignKey("company.company_id"), index=True)
    taxonomy_or_account: Mapped[str] = mapped_column(String(100), comment="us-gaap tag 或 CN 科目")
    concept: Mapped[str] = mapped_column(String(150))
    unit: Mapped[str | None] = mapped_column(String(20))
    period_end: Mapped[date] = mapped_column(Date)
    value: Mapped[float | None] = mapped_column(Float)
    available_date: Mapped[date | None] = mapped_column(Date, comment="信息可得日期")
    source_type: Mapped[str | None] = mapped_column(String(20))
    source_id: Mapped[str | None] = mapped_column(String(64))

    company: Mapped["Company"] = relationship(back_populates="facts")

    __table_args__ = (
        Index("ix_fact_company_concept_period", "company_id", "concept", "period_end"),
    )
