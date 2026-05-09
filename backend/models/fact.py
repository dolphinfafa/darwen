# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Float, Date, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Fact(Base):
    __tablename__ = "fact"

    fact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    account_code: Mapped[str] = mapped_column(
        String(100), comment="us-gaap tag 或 CN 科目（统一为 canonical 字段名）"
    )
    concept: Mapped[str] = mapped_column(String(150), comment="原始字段含义/标签")
    unit: Mapped[str | None] = mapped_column(String(20))
    period_end: Mapped[date] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(
        Integer, comment="财年（用于 5Y/10Y 序列计算）"
    )
    value: Mapped[float | None] = mapped_column(Float)
    available_date: Mapped[date | None] = mapped_column(
        Date, comment="信息可得日期（向后兼容字段）"
    )
    accepted_date: Mapped[date | None] = mapped_column(
        Date, comment="filing accepted/actual 披露日，点时回测核心字段"
    )
    source_type: Mapped[str | None] = mapped_column(String(20))
    source_id: Mapped[str | None] = mapped_column(String(64))
    amended_from_fact_id: Mapped[str | None] = mapped_column(
        String(128), comment="若为更正后版本，记录原 fact_id"
    )

    company: Mapped["Company"] = relationship(back_populates="facts")

    __table_args__ = (
        Index("ix_fact_company_account_period", "company_id", "account_code", "period_end"),
        Index("ix_fact_accepted_date", "accepted_date"),
    )
