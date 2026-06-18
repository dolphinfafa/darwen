# -*- coding: utf-8 -*-
"""我的股票池（持久化 watchlist）。

- Watchlist：用户的一个命名股票池
- WatchlistItem：池内一只股票（可记录来源筛选 run + 备注）
"""
from datetime import datetime

from sqlalchemy import (
    String, DateTime, ForeignKey, BigInteger, Integer, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("watchlist.id"), index=True
    )
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    source_run_id: Mapped[int | None] = mapped_column(BigInteger, comment="来源筛选 run（可空）")
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_company"),
    )
