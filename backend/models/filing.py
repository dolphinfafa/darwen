# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Filing(Base):
    __tablename__ = "filing"

    filing_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(32), ForeignKey("company.company_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), comment="SEC|SSE|CNINFO|SSEINFO")
    form_type: Mapped[str | None] = mapped_column(String(30), comment="10-K, 10-Q, 年报, etc.")
    filed_date: Mapped[date | None] = mapped_column(Date)
    available_date: Mapped[date | None] = mapped_column(Date, comment="信息可得日期（防前视）")
    url: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))

    company: Mapped["Company"] = relationship(back_populates="filings")
