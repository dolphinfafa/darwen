# -*- coding: utf-8 -*-
"""AI 风险层调度器。

接口：
    analyze_risk(db, company_id, asof_date, run_id, user_id, rule_triggered, ...) -> RiskAIResult

流程：
1. 取 user 的 ai_provider_default + 解密对应 key
2. 取 company 财务摘要（roce/cfo_ni/net_debt/...）
3. 取 company text_document（最近 N 份，按 published_at desc）
4. 构造 prompt（PROMPT_VERSION + 业务上下文）
5. 调 provider.call()，timeout 20s
6. JSON 解析 + Pydantic 校验；失败重试 1 次
7. PRD 第 6 节融合规则：REJECT 仅当高置信 + 法定披露 + 硬规则同向
8. 写 risk_ai_result（prompt_hash / latency_ms / 原始响应快照）
9. 返回 RiskAIResult ORM

降级：
- 用户未绑定 key                  → RuleOnlyResult(reason="NO_USER_KEY")
- 两个 provider 都失败            → RuleOnlyResult(reason="ALL_PROVIDERS_FAILED")
- JSON 校验重试仍失败             → RuleOnlyResult(reason="INVALID_JSON_AFTER_RETRY")
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.metric_periodic import MetricPeriodic
from backend.models.risk_ai_result import RiskAIResult
from backend.models.text_document import TextDocument
from backend.models.user import User

from backend.ai.crypto import InvalidToken, decrypt_api_key
from backend.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, STURDINESS_SYSTEM_PROMPT, build_user_prompt
from backend.ai.provider_base import (
    AIAuthError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
)
from backend.ai.schema import RiskAIOutput


log = logging.getLogger(__name__)


# 法定披露 source_type 集合（PRD 第 6 节证据优先级）
LEGAL_DISCLOSURE_SOURCES = frozenset({"SEC", "CNINFO", "EXCH", "TS-ANN"})


@dataclass
class RuleOnlyResult:
    """AI 不可用或调用失败时的降级结果。"""
    reason: str
    error_msg: Optional[str] = None
    ai_result_id: None = None
    overall_action: str = "RULE_ONLY"


@dataclass
class AIResult:
    """AI 成功返回的结果。"""
    ai_result_id: int
    overall_action: str  # PASS / REVIEW / REJECT / MONITOR
    output: RiskAIOutput


# ---------------- Provider 工厂 ----------------

def _build_provider(user: User, provider_name: Optional[str] = None) -> Optional[AIProvider]:
    """根据 user 配置实例化 provider。未绑定 key 返回 None。"""
    name = provider_name or user.ai_provider_default or "chatgpt"

    if name == "chatgpt":
        if not user.chatgpt_api_key_encrypted:
            return None
        try:
            key = decrypt_api_key(user.chatgpt_api_key_encrypted)
        except (InvalidToken, ValueError) as e:
            log.warning("decrypt chatgpt key failed: %s", e)
            return None
        from backend.ai.chatgpt_provider import ChatGPTProvider
        return ChatGPTProvider(api_key=key)

    if name == "minimax":
        if not user.minimax_api_key_encrypted or not user.minimax_group_id:
            return None
        try:
            key = decrypt_api_key(user.minimax_api_key_encrypted)
        except (InvalidToken, ValueError) as e:
            log.warning("decrypt minimax key failed: %s", e)
            return None
        from backend.ai.minimax_provider import MiniMaxProvider
        return MiniMaxProvider(api_key=key, group_id=user.minimax_group_id)

    log.warning("unknown provider name: %s", name)
    return None


def _build_fallback_provider(user: User, primary: str) -> Optional[AIProvider]:
    """主 provider 失败时尝试另一家。"""
    alt = "minimax" if primary == "chatgpt" else "chatgpt"
    return _build_provider(user, provider_name=alt)


# ---------------- 业务上下文构造 ----------------

def _build_financial_summary(
    db: Session,
    company_id: str,
    asof_date: date,
) -> dict:
    """从 metric_periodic 取最近的截面值汇总。"""
    metric_names = [
        "roce_5y_median", "roce_10y_median", "q3_pass_5y", "q4_strong_track_record",
        "cfo_ni_5y_consec_below_07", "cfo_ni_5y_below_07_years", "fcf_neg_5y_years", "median_cfo_ni_5y",
        "net_debt_ebit", "interest_coverage", "current_ratio",
        "share_count_cagr_5y",
        "pe_ttm", "ev_ebit", "market_cap",
    ]
    out: dict = {}
    for name in metric_names:
        row = db.execute(
            select(MetricPeriodic.value)
            .where(
                and_(
                    MetricPeriodic.company_id == company_id,
                    MetricPeriodic.metric_name == name,
                    MetricPeriodic.period_end <= asof_date,
                )
            )
            .order_by(MetricPeriodic.period_end.desc())
            .limit(1)
        ).first()
        if row and row.value is not None:
            out[name] = round(float(row.value), 6)
    return out


def _load_recent_documents(
    db: Session,
    company_id: str,
    asof_date: date,
    *,
    limit: int = 10,
) -> list[dict]:
    """读取 text_document 最近 limit 份，按 published_at desc。

    每份返回简化 dict（doc_id / source_type / doc_type / title /
    published_at / content_text）。
    """
    rows = db.execute(
        select(TextDocument)
        .where(
            and_(
                TextDocument.company_id == company_id,
                TextDocument.published_at.isnot(None),
            )
        )
        .order_by(TextDocument.published_at.desc())
        .limit(limit)
    ).scalars().all()

    out = []
    for d in rows:
        published_dt = d.published_at
        if published_dt and published_dt.date() > asof_date:
            continue  # 点时严格：跳过未来
        out.append({
            "doc_id": f"doc_{d.doc_id}",
            "source_type": d.source_type,
            "doc_type": d.doc_type,
            "title": d.title or "",
            "published_at": published_dt.date().isoformat() if published_dt else "",
            "content_text": (d.content_text or "")[:2000],
        })
    return out


def _legal_doc_ids(docs: list[dict]) -> set[str]:
    """从文档列表抽出法定披露的 doc_id 集合。"""
    return {
        d["doc_id"] for d in docs
        if d.get("source_type") in LEGAL_DISCLOSURE_SOURCES
    }


# ---------------- 核心调用 ----------------

def _call_with_retry(
    provider: AIProvider,
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: float = 20.0,
    temperature: float = 0.1,
) -> tuple[Optional[RiskAIOutput], Optional[str], Optional[str], int]:
    """调 provider 并校验 JSON，失败重试 1 次。

    返回 (parsed_output, raw_text, error_msg, total_latency_ms)
    """
    last_err: Optional[str] = None
    last_raw: Optional[str] = None
    total_ms = 0

    for attempt in range(2):
        t0 = time.monotonic()
        try:
            raw = provider.call(system_prompt, user_prompt, timeout=timeout, temperature=temperature)
        except (AITimeoutError, AIAuthError, AIProviderError) as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            total_ms += elapsed
            last_err = f"{type(e).__name__}: {e}"
            log.warning("provider call attempt %d failed: %s", attempt + 1, last_err)
            if isinstance(e, AIAuthError):
                # auth 错误不重试
                return None, None, last_err, total_ms
            continue

        elapsed = int((time.monotonic() - t0) * 1000)
        total_ms += elapsed
        last_raw = raw
        try:
            parsed = json.loads(raw)
            return RiskAIOutput.model_validate(parsed), raw, None, total_ms
        except json.JSONDecodeError as e:
            last_err = f"JSONDecodeError: {e}"
            log.warning("provider call attempt %d non-json: %s", attempt + 1, e)
        except ValidationError as e:
            last_err = f"ValidationError: {e}"
            log.warning("provider call attempt %d schema invalid: %s", attempt + 1, e)

    return None, last_raw, last_err, total_ms


# ---------------- PRD 融合规则 ----------------

def _fuse_action(
    ai_output: RiskAIOutput,
    rule_triggered_hard: bool,
    legal_doc_ids: set[str],
) -> str:
    """PRD 第 6 节融合规则：

    - REJECT 仅当：高置信(≥0.8) 且 法定披露证据 或 硬规则同向触发
    - REVIEW：任一中/高风险标签 或 RULE_ONLY 含软触发
    - PASS：无中/高风险
    - MONITOR：事件型风险但不阻止
    """
    action = ai_output.overall_action

    if action == "REJECT":
        max_conf = ai_output.max_confidence()
        if max_conf >= 0.8 and (
            ai_output.has_legal_disclosure_evidence(legal_doc_ids) or rule_triggered_hard
        ):
            return "REJECT"
        # 否则降级 REVIEW
        return "REVIEW"

    return action  # PASS / REVIEW / MONITOR 直接透传


# ---------------- 入口 ----------------

_LAYER_SYSTEM = {"sturdiness": STURDINESS_SYSTEM_PROMPT, "risk": SYSTEM_PROMPT}


def analyze_layer(
    db: Session,
    *,
    company_id: str,
    asof_date: date,
    user_id: int,
    run_id: Optional[int],
    rule_triggered: dict,
    layer: str = "risk",
    provider_override: Optional[str] = None,
    timeout: float = 20.0,
    temperature: float = 0.1,
) -> AIResult | RuleOnlyResult:
    """编排单股某一层（sturdiness|risk）的 AI 判定。"""
    system_prompt = _LAYER_SYSTEM.get(layer, SYSTEM_PROMPT)
    user = db.get(User, user_id)
    if user is None:
        return RuleOnlyResult(reason="USER_NOT_FOUND")

    company = db.get(Company, company_id)
    if company is None:
        return RuleOnlyResult(reason="COMPANY_NOT_FOUND")

    primary_name = provider_override or user.ai_provider_default or "chatgpt"
    provider = _build_provider(user, provider_name=primary_name)
    if provider is None:
        return RuleOnlyResult(reason="NO_USER_KEY")

    # 构造业务上下文
    financial_summary = _build_financial_summary(db, company_id, asof_date)
    docs = _load_recent_documents(db, company_id, asof_date, limit=10)
    legal_ids = _legal_doc_ids(docs)
    ticker = company.cik or company.stock_code or company.company_id
    user_prompt = build_user_prompt(
        ticker=ticker,
        market=company.market,
        as_of_date=asof_date.isoformat(),
        industry=company.industry_name,
        business_summary=None,
        financial_summary=financial_summary,
        docs=docs,
        rule_triggered=rule_triggered,
    )
    prompt_hash = hashlib.sha256(
        (system_prompt + user_prompt).encode("utf-8")
    ).hexdigest()

    # 调主 provider
    parsed, raw, err, latency_ms = _call_with_retry(
        provider, system_prompt, user_prompt, timeout=timeout, temperature=temperature,
    )

    # 主失败 → 尝试备用 provider
    if parsed is None:
        fallback = _build_fallback_provider(user, primary_name)
        if fallback is not None:
            parsed2, raw2, err2, latency2 = _call_with_retry(
                fallback, system_prompt, user_prompt, timeout=timeout, temperature=temperature,
            )
            if parsed2 is not None:
                parsed = parsed2
                raw = raw2
                err = None
                latency_ms += latency2
                provider = fallback
            else:
                err = f"primary={err}; fallback={err2}"
                latency_ms += latency2

    if parsed is None:
        # 持久化失败记录（不写 labels）
        row = RiskAIResult(
            company_id=company_id,
            run_id=run_id,
            asof_date=asof_date,
            layer=layer,
            ai_provider=provider.name,
            model_name=provider.model,
            prompt_version=PROMPT_VERSION,
            prompt_hash=prompt_hash,
            overall_action="REVIEW",  # 失败时按 PRD 强制 REVIEW
            labels=None,
            summary_cn=None,
            raw_response={"raw": raw[:5000] if raw else None, "error": err},
            latency_ms=latency_ms,
            error_msg=(err or "")[:500],
        )
        db.add(row)
        db.commit()
        return RuleOnlyResult(
            reason="INVALID_JSON_AFTER_RETRY" if raw else "ALL_PROVIDERS_FAILED",
            error_msg=err,
        )

    # 融合 PRD 规则
    fused_action = _fuse_action(
        parsed,
        rule_triggered_hard=bool(rule_triggered.get("hard_triggered", False)),
        legal_doc_ids=legal_ids,
    )

    # 落库 risk_ai_result
    row = RiskAIResult(
        company_id=company_id,
        run_id=run_id,
        asof_date=asof_date,
        layer=layer,
        ai_provider=provider.name,
        model_name=provider.model,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash,
        overall_action=fused_action,
        labels=[lbl.model_dump() for lbl in parsed.labels],
        summary_cn=parsed.summary_cn,
        raw_response={"raw": raw[:5000] if raw else None, "parsed": parsed.model_dump()},
        latency_ms=latency_ms,
        error_msg=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AIResult(ai_result_id=row.result_id, overall_action=fused_action, output=parsed)


def analyze_risk(db: Session, **kwargs) -> AIResult | RuleOnlyResult:
    """兼容旧 R 层入口：等价 analyze_layer(layer='risk')。"""
    kwargs.pop("layer", None)
    return analyze_layer(db, layer="risk", **kwargs)
