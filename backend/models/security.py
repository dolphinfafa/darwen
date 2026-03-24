# -*- coding: utf-8 -*-
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Security(Base):
    __tablename__ = "security"

    security_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(32), ForeignKey("company.company_id"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str | None] = mapped_column(String(20))
    isin: Mapped[str | None] = mapped_column(String(20))

    company: Mapped["Company"] = relationship(back_populates="securities")
    market_bars: Mapped[list["MarketBar"]] = relationship(back_populates="security")
