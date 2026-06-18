# -*- coding: utf-8 -*-
"""AI 风险标签输出表"""
from datetime import date, datetime

from sqlalchemy import String, DateTime, Date, ForeignKey, Index, Text, BigInteger, Integer, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import JSON

from backend.database import Base


class RiskAIResult(Base):
    __tablename__ = "risk_ai_result"

    result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("screen_run.run_id"), index=True
    )
    asof_date: Mapped[date] = mapped_column(Date, index=True)

    layer: Mapped[str | None] = mapped_column(
        String(20), index=True,
        comment="sturdiness|risk —— funnel_v2 哪一层的 AI 判定；NULL=旧 R 层",
    )

    ai_provider: Mapped[str] = mapped_column(
        Enum("chatgpt", "minimax", name="ai_provider_result_enum")
    )
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    prompt_hash: Mapped[str] = mapped_column(String(64), comment="prompt 文本的 sha256")

    overall_action: Mapped[str] = mapped_column(
        Enum("PASS", "REVIEW", "REJECT", "MONITOR", name="ai_action_enum")
    )
    labels: Mapped[dict | None] = mapped_column(
        JSON,
        comment="[{label, severity, confidence, evidence_doc_ids[], short_reason}]",
    )
    summary_cn: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict | None] = mapped_column(JSON, comment="原始 AI 响应快照")

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_msg: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_risk_ai_company_asof", "company_id", "asof_date"),
    )
