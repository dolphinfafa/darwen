# -*- coding: utf-8 -*-
"""治理硬事实信号表（governance_signal）。

阶段 2：把第三层「治理 AI 标签」升级为「硬事实优先、AI 佐证」。
通用结构，容纳多来源治理红旗——
- 美股 SEC 8-K：Item 4.02 财务重述 / 4.01 审计师更换 / 5.02 高管董事离任
- 美股 SEC Form 4：内部人交易（后续）
- A股 Tushare：pledge_stat 质押 / top10_holders 股东集中 / stk_managers 管理层变动（后续）

点时可见性以 event_date 为准（筛选只看 event_date ≤ as_of 的信号）。
"""
from datetime import datetime

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class GovernanceSignal(Base):
    __tablename__ = "governance_signal"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    # restatement / auditor_change / exec_departure / share_pledge /
    # insider_selling / holder_concentration / holder_count_drop ...
    signal_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(10))   # hard / soft / info
    event_date: Mapped[Date] = mapped_column(Date, index=True)  # 点时可见性基准
    value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 数值信号（质押率/次数/金额）
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30))  # SEC-8K / SEC-Form4 / TS-pledge ...
    source_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_govsig_company_type", "company_id", "signal_type"),
        Index("ix_govsig_company_event", "company_id", "event_date"),
    )
