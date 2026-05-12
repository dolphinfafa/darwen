# -*- coding: utf-8 -*-
"""AI 风险层 JSON 输出 schema（PRD 第 4.5 节）。

Pydantic 校验从 ChatGPT / MiniMax 返回的 JSON：
- 非 JSON 或字段缺失抛 ValidationError → orchestrator 重试 1 次
- 重试仍失败 → 降级 RULE_ONLY
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


SeverityLevel = Literal["low", "medium", "high"]
OverallAction = Literal["PASS", "REVIEW", "REJECT", "MONITOR"]

# PRD 第 4.5 节定义的 9 类风险标签
KNOWN_LABELS = {
    "governance_risk",
    "accounting_risk",
    "regulatory_risk",
    "turnaround_risk",
    "serial_acquirer_risk",
    "customer_concentration_risk",
    "supplier_concentration_risk",
    "disruption_risk",
    "minority_shareholder_risk",
}


class RiskLabel(BaseModel):
    label: str
    severity: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    short_reason: str = ""

    @field_validator("label")
    @classmethod
    def _validate_label(cls, v: str) -> str:
        # 不强制白名单（容错），但记录未知标签供后续 prompt 调优
        return v.strip()


class RiskAIOutput(BaseModel):
    """AI 风险层完整输出，落入 risk_ai_result 表。"""
    ticker: str
    market: str
    as_of_date: str  # ISO 8601 YYYY-MM-DD
    overall_action: OverallAction
    summary_cn: str = ""
    labels: list[RiskLabel] = Field(default_factory=list)
    manual_review_required: bool = False

    @field_validator("overall_action", mode="before")
    @classmethod
    def _normalize_action(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v

    def has_legal_disclosure_evidence(
        self,
        legal_doc_ids: set[str],
    ) -> bool:
        """检查是否至少有一个 label 的证据 doc_id 来自法定披露。

        用于融合规则：REJECT 需要高置信 + 法定披露支撑。
        """
        for lbl in self.labels:
            if any(eid in legal_doc_ids for eid in lbl.evidence_doc_ids):
                return True
        return False

    def max_confidence(self) -> float:
        """返回所有 label 中的最高 confidence。"""
        if not self.labels:
            return 0.0
        return max(lbl.confidence for lbl in self.labels)


class AICallStats(BaseModel):
    """AI 调用统计，供 orchestrator 落 risk_ai_result。"""
    latency_ms: int
    prompt_hash: str
    model_name: str
    temperature: float
    error_msg: Optional[str] = None
