# -*- coding: utf-8 -*-
"""风险过滤 prompt 模板（PRD 第 4.5 节）。

输出严格 JSON Schema：
{
  "ticker": "AAPL",
  "market": "US",
  "as_of_date": "2026-05-12",
  "overall_action": "PASS|REVIEW|REJECT|MONITOR",
  "summary_cn": "...",
  "labels": [
    {
      "label": "customer_concentration_risk",
      "severity": "low|medium|high",
      "confidence": 0.0-1.0,
      "evidence_doc_ids": ["doc_xxx"],
      "short_reason": "..."
    }
  ],
  "manual_review_required": false
}
"""
from __future__ import annotations

import json
from typing import Optional


SYSTEM_PROMPT = """你是 Darwen 风险过滤器。你的任务不是推荐买卖，而是识别"是否存在应阻止继续研究或要求人工覆核的重大风险"。

工作准则：
1. 你只能从输入的证据材料中得出结论，不得引用未提供的外部信息。
2. 你只能从以下 9 类标签中选择：
   - governance_risk            治理风险（董事会冲突、关联交易、控制权异常）
   - accounting_risk            会计/审计风险（非标审计、重大重述）
   - regulatory_risk            监管/处罚风险（立案调查、监管函、重大处罚）
   - turnaround_risk            转型/反转陷阱（5Y 历史差但近 1-2 年改善 + restructuring 叙事）
   - serial_acquirer_risk       并购成瘾（频繁并购 + 商誉/资产抬升 + ROCE 下滑）
   - customer_concentration_risk 客户集中（top1>25% 或 top5>50%）
   - supplier_concentration_risk 供应商集中
   - disruption_risk            行业/技术断裂风险（护城河被打断）
   - minority_shareholder_risk  少数股东不友好（资金占用、违规担保、定增稀释）
3. 对每个识别出的标签输出：severity（low/medium/high）、confidence（0-1）、evidence_doc_ids（必须引用输入提供的 doc_id）、short_reason（中文 1-2 句）。
4. overall_action：
   - PASS：无高/中风险标签
   - MONITOR：有事件型风险但不阻止继续研究
   - REVIEW：任一中/高风险标签触发，或与硬规则信号冲突
   - REJECT：高置信(confidence ≥ 0.8) + 法定披露/监管文书证据 + 风险足以阻止研究
5. 若仅有新闻类证据（无法定披露 / 公告 / 监管文书支撑），最高只能给 REVIEW。
6. 必须用中文撰写 summary_cn。不得输出买卖建议或目标价位。
7. 严格按 JSON 输出，不要任何 Markdown 包裹、不要前后解释文字、不要 ```json``` 代码块标记。
"""


def _format_docs(docs: list[dict]) -> str:
    """把文档列表格式化为 prompt 内嵌文本块。"""
    if not docs:
        return "（无可用文档）"
    lines = []
    for d in docs:
        doc_id = d.get("doc_id", "?")
        title = d.get("title", "无标题")
        published = d.get("published_at", "")
        source = d.get("source_type", "?")
        doc_type = d.get("doc_type", "?")
        text = d.get("content_text") or d.get("snippet") or ""
        text = (text[:2000] + "…") if len(text) > 2000 else text
        lines.append(
            f"--- doc_id={doc_id} | {source}/{doc_type} | {published} ---\n"
            f"标题: {title}\n"
            f"正文: {text}\n"
        )
    return "\n".join(lines)


def _format_signals(signals: dict) -> str:
    """格式化已触发的硬规则信号供 AI 参考。"""
    if not signals:
        return "（无硬规则触发）"
    items = [f"- {k}: {v}" for k, v in signals.items()]
    return "\n".join(items)


def build_user_prompt(
    ticker: str,
    market: str,
    as_of_date: str,
    industry: Optional[str],
    business_summary: Optional[str],
    financial_summary: dict,
    docs: list[dict],
    rule_triggered: dict,
) -> str:
    """构造 user prompt。

    financial_summary 例：
        {
          "roce_5y_median": 0.297, "roce_10y_median": 0.213,
          "cfo_ni_ratio_5y": 1.15, "fcf_neg_5y_years": 0,
          "net_debt_ebit": 0.32, "interest_coverage": 23.1,
          "share_count_cagr_5y": -0.007,
          "pe_ttm": 35.2,
        }
    docs 例：
        [{"doc_id":"doc_1021","source_type":"SEC","doc_type":"10-K",
          "published_at":"2024-07-30","title":"...","content_text":"..."}, ...]
    rule_triggered 例：
        {"R1_HIGH_LEVERAGE": True, "R3_HIGH_DILUTION": False, ...}
    """
    return f"""请基于以下材料完成风险识别。

【1. 基础信息】
ticker: {ticker}
市场: {market}
行业: {industry or "未提供"}
主营业务摘要: {business_summary or "未提供"}
as_of_date: {as_of_date}

【2. 点时财务摘要】
{json.dumps(financial_summary, ensure_ascii=False, indent=2)}

【3. 文档列表（按时间倒序）】
{_format_docs(docs)}

【4. 规则引擎已触发的硬信号】
{_format_signals(rule_triggered)}

【任务】
按系统提示输出 JSON，字段 ticker、market、as_of_date、overall_action、summary_cn、labels（数组）、manual_review_required（布尔）。
"""


__all__ = ["SYSTEM_PROMPT", "build_user_prompt"]
