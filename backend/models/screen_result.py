# -*- coding: utf-8 -*-
"""单次筛选结果表（每只股票一行）"""
from sqlalchemy import String, ForeignKey, Index, BigInteger, Integer, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import JSON

from backend.database import Base


class ScreenResult(Base):
    __tablename__ = "screen_result"

    result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("screen_run.run_id"), index=True
    )
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("company.company_id"), index=True
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "Rejected",
            "Review",
            "TooExpensive",
            "NearFairPrice",
            "HighConviction",
            name="screen_status_enum",
        ),
        index=True,
    )

    q_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    q_strong_track: Mapped[bool] = mapped_column(Boolean, default=False)
    r_action: Mapped[str | None] = mapped_column(
        Enum("PASS", "REVIEW", "REJECT", "MONITOR", "RULE_ONLY", name="r_action_enum")
    )
    v_state: Mapped[str | None] = mapped_column(
        Enum("TooExpensive", "Acceptable", "Cheap", name="v_state_enum")
    )

    reason_codes: Mapped[list | None] = mapped_column(
        JSON,
        comment="['Q3_FAIL', 'R1_LEVERAGE', 'V2_PASS', ...]",
    )
    metrics_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        comment="{roce_5y_median, pe_ttm, net_debt_ebit, cfo_ni_5y, ...}",
    )
    ai_result_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("risk_ai_result.result_id")
    )
    rank: Mapped[int | None] = mapped_column(Integer)

    # 三层漏斗（funnel_v2）：ROCE → 稳健性 → 风险性
    rejected_at_layer: Mapped[str | None] = mapped_column(
        String(20),
        index=True,
        comment="roce|sturdiness|risk —— 在哪层被过滤；NULL=当前存活/最终入选",
    )
    layer_results: Mapped[dict | None] = mapped_column(
        JSON,
        comment="{roce:{passed,reason_codes,metrics}, sturdiness:{...}, risk:{...}} 逐层结果",
    )
    manual_action: Mapped[dict | None] = mapped_column(
        JSON,
        comment="人工干预 {layer, action: force_pass|force_reject, note, at}",
    )

    __table_args__ = (
        Index("ix_screen_result_run_status", "run_id", "status"),
        Index("ix_screen_result_company_run", "company_id", "run_id"),
        Index("ix_screen_result_run_layer", "run_id", "rejected_at_layer"),
    )
