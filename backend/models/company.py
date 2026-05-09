# -*- coding: utf-8 -*-
from datetime import date

from sqlalchemy import String, Enum, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    market: Mapped[str] = mapped_column(Enum("US", "CN_A", name="market_enum"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str | None] = mapped_column(String(200))
    industry_code: Mapped[str | None] = mapped_column(String(50), index=True)
    industry_name: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    cik: Mapped[str | None] = mapped_column(String(20), unique=True, comment="SEC CIK (美股)")
    stock_code: Mapped[str | None] = mapped_column(String(20), comment="A股代码 (如 600519)")

    instrument_type: Mapped[str] = mapped_column(
        Enum(
            "COMMON", "REIT", "ETF", "FUND", "SPAC", "ADR", "PREFERRED", "WARRANT",
            "BANK", "INSURANCE", "BROKER", "SHELL", "OTHER",
            name="instrument_type_enum",
        ),
        default="COMMON",
        index=True,
        comment="证券类型，用于 Q0 非适用证券过滤",
    )
    list_date: Mapped[date | None] = mapped_column(Date, comment="上市日期")
    is_excluded: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否被强制排除（管理员标记）"
    )

    securities: Mapped[list["Security"]] = relationship(back_populates="company")
    filings: Mapped[list["Filing"]] = relationship(back_populates="company")
    facts: Mapped[list["Fact"]] = relationship(back_populates="company")
