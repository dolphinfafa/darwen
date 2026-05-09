# -*- coding: utf-8 -*-
"""公告/年报/新闻原文文档表"""
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Index, Text, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TextDocument(Base):
    __tablename__ = "text_document"

    doc_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(20), comment="SEC|CNINFO|EXCH|TS-ANN|PG-NEWS"
    )
    doc_type: Mapped[str] = mapped_column(
        String(40),
        comment="10-K|10-Q|8-K|annual|interim|regulatory|news|other",
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500))
    content_text: Mapped[str | None] = mapped_column(
        Text, comment="原文文本（截断后）"
    )
    content_url: Mapped[str | None] = mapped_column(String(500))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    filing_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("filing.filing_id"), comment="如来自 filing 则关联"
    )

    __table_args__ = (
        Index("ix_text_doc_company_published", "company_id", "published_at"),
        Index("ix_text_doc_company_doctype", "company_id", "doc_type"),
    )
