# -*- coding: utf-8 -*-
"""市场资讯（Tushare major_news 大盘新闻，全市场非个股）。"""
from datetime import datetime

from sqlalchemy import String, DateTime, Text, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MarketNews(Base):
    __tablename__ = "market_news"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(500), unique=True, index=True)
    source: Mapped[str | None] = mapped_column(String(60))
    content: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
