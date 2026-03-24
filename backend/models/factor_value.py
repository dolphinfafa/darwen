# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Float, Date, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class FactorValue(Base):
    __tablename__ = "factor_value"

    factor_value_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(32), ForeignKey("company.company_id"), index=True)
    factor_code: Mapped[str] = mapped_column(String(10), index=True, comment="S1, R1, M1, etc.")
    asof_date: Mapped[date] = mapped_column(Date)
    raw_value: Mapped[float | None] = mapped_column(Float)
    cleaned_value: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float, comment="归一化后 0-100 分")
    normalization_bucket: Mapped[str | None] = mapped_column(String(100), comment="行业×市值桶")
    lineage: Mapped[str | None] = mapped_column(Text, comment="inputs->rules 血缘")

    company: Mapped["Company"] = relationship(back_populates="factor_values")

    __table_args__ = (
        Index("ix_fv_company_factor_date", "company_id", "factor_code", "asof_date"),
    )
