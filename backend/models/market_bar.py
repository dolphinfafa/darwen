# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Float, Date, BigInteger, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class MarketBar(Base):
    __tablename__ = "market_bar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(String(32), ForeignKey("security.security_id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)

    security: Mapped["Security"] = relationship(back_populates="market_bars")

    __table_args__ = (
        Index("ix_mb_security_date", "security_id", "trade_date", unique=True),
    )
