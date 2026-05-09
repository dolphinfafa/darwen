# -*- coding: utf-8 -*-
from datetime import date, datetime

from sqlalchemy import String, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Filing(Base):
    __tablename__ = "filing"

    filing_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(20), comment="SEC|CNINFO|SSE|SZSE|TS-ANN"
    )
    form_type: Mapped[str | None] = mapped_column(
        String(30), comment="10-K, 10-Q, 8-K, 年报, 季报, 临时公告, etc."
    )
    title: Mapped[str | None] = mapped_column(
        String(500), comment="公告/披露标题"
    )
    filed_date: Mapped[date | None] = mapped_column(Date, comment="filer 提交日期")
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="SEC accepted_at / 交易所收文时间"
    )
    actual_disclosure_date: Mapped[date | None] = mapped_column(
        Date, comment="A 股 actual_date / 美股 effective filing date"
    )
    available_date: Mapped[date | None] = mapped_column(
        Date, comment="信息可得日期（防前视，等价于 accepted_at 的日历日）"
    )
    url: Mapped[str | None] = mapped_column(String(500), comment="filing 详情/索引页 URL")
    url_pdf: Mapped[str | None] = mapped_column(String(500), comment="原文 PDF 链接")
    sha256: Mapped[str | None] = mapped_column(String(64))

    company: Mapped["Company"] = relationship(back_populates="filings")

    __table_args__ = (
        Index("ix_filing_company_form", "company_id", "form_type"),
        Index("ix_filing_accepted_at", "accepted_at"),
    )
