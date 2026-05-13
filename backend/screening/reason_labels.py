# -*- coding: utf-8 -*-
"""reason_code 中文 label + 详细描述（前端展示用）。

每个 reason_code 映射到：
- label: 短中文标签（2-6 字，前端 pill 显示）
- desc:  详细解释（一句话，前端 tooltip）
- layer: 所属漏斗层（Q / R / V / AI / META）
- severity: info / warning / error（影响前端颜色）

新增 reason_code 时必须同步在此添加映射。
"""
from __future__ import annotations

from typing import Literal, TypedDict


Severity = Literal["info", "warning", "error"]
Layer = Literal["Q", "R", "V", "AI", "META"]


class LabelEntry(TypedDict):
    label: str
    desc: str
    layer: Layer
    severity: Severity


REASON_LABELS: dict[str, LabelEntry] = {
    # ============ Q0 排除 ============
    "Q0_EXCLUDED_BANK": {"label": "银行排除", "desc": "Q0 非适用证券：商业银行（ROCE 口径不适用，PRD 第 5 节）", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_INSURANCE": {"label": "保险排除", "desc": "Q0 非适用：保险公司", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_BROKER": {"label": "券商排除", "desc": "Q0 非适用：证券/经纪商", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_REIT": {"label": "REIT 排除", "desc": "Q0 非适用：房地产投资信托", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_ETF": {"label": "ETF 排除", "desc": "Q0 非适用：交易型开放式基金", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_FUND": {"label": "基金排除", "desc": "Q0 非适用：投资基金", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_SPAC": {"label": "SPAC 排除", "desc": "Q0 非适用：特殊目的收购公司（无运营历史）", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_ADR": {"label": "ADR 排除", "desc": "Q0 非适用：美国存托凭证", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_PREFERRED": {"label": "优先股排除", "desc": "Q0 非适用：优先股", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_WARRANT": {"label": "权证排除", "desc": "Q0 非适用：认股权证", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_SHELL": {"label": "壳公司排除", "desc": "Q0 非适用：壳公司", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_OTHER": {"label": "其他类型排除", "desc": "Q0 非适用：其他特殊证券类型", "layer": "Q", "severity": "error"},
    "Q0_EXCLUDED_FLAG": {"label": "管理员排除", "desc": "Q0：管理员手动标记 is_excluded=True", "layer": "Q", "severity": "error"},

    # ============ Q1-Q6 质量层 ============
    "Q1_INSUFFICIENT_HISTORY": {"label": "财年不足", "desc": "Q1：可见财年 < 5 年，无法做 5Y ROCE 中位数判定", "layer": "Q", "severity": "warning"},
    "Q3_PASS": {"label": "Q3 通过", "desc": "Q3：5Y ROCE 中位数 ≥ 20% 且至少 4 年达标", "layer": "Q", "severity": "info"},
    "Q3_FAIL_MEDIAN": {"label": "ROCE 中位低", "desc": "Q3 不过：5Y ROCE 中位数 < 阈值（默认 20%）", "layer": "Q", "severity": "error"},
    "Q3_FAIL_COUNT": {"label": "ROCE 不稳", "desc": "Q3 不过：5Y 中位达标但满足年数 < 4/5（波动太大）", "layer": "Q", "severity": "error"},
    "Q4_STRONG_TRACK_RECORD": {"label": "10Y 强通过", "desc": "Q4：10 年中至少 8 年 ROCE ≥ 20%，10Y 中位数 ≥ 20%（顶级公司标签）", "layer": "Q", "severity": "info"},
    "Q5_NEGATIVE_CAPITAL_EMPLOYED": {"label": "负营运资本", "desc": "Q5：近 5 年内有 ≥2 年 CapitalEmployed ≤ 0（结构性负 NWC，需人工覆核）", "layer": "Q", "severity": "warning"},
    "Q6_LIST_DATE_TOO_RECENT": {"label": "新上市", "desc": "Q6：上市未满 5 年，历史数据不足", "layer": "Q", "severity": "warning"},

    # ============ R1-R3 硬规则 ============
    "R1_HIGH_LEVERAGE": {"label": "高杠杆", "desc": "R1：net_debt/EBIT 超阈值（默认 standard 4 倍 / strict 3 倍）", "layer": "R", "severity": "error"},
    "R1_LOW_COVERAGE": {"label": "利息保障低", "desc": "R1：interest_coverage < 阈值（standard 3x / strict 4x），可能含亏损公司 EBIT<0 致负值", "layer": "R", "severity": "error"},
    "R1_DETERIORATING_LIQUIDITY": {"label": "流动性恶化", "desc": "R1：current_ratio < 1 且最近 2-3 年连续下滑", "layer": "R", "severity": "warning"},
    "R2_POOR_CFO_NI": {"label": "现金质量差", "desc": "R2：CFO/NetIncome 连续 < 0.7（盈利质量低，可能为应计项操纵）", "layer": "R", "severity": "warning"},
    "R2_PERSISTENT_FCF_NEGATIVE": {"label": "FCF 长期负", "desc": "R2：5 年内 FCF<0 ≥ 3 年（持续烧钱或重资本扩张）", "layer": "R", "severity": "warning"},
    "R3_HIGH_DILUTION": {"label": "高频稀释", "desc": "R3：5Y 股本 CAGR 超阈值（standard 3% / strict 2%）且 ROCE 未改善", "layer": "R", "severity": "warning"},
    "R4_SERIAL_ACQUIRER": {"label": "并购成瘾", "desc": "R4：3Y 大额并购 + 商誉抬升 + ROCE 下滑（需 AI 判定）", "layer": "R", "severity": "warning"},
    "R5_AUDIT_ISSUE": {"label": "审计问题", "desc": "R5：非标审计意见 / 重大重述（AI 从 10-K 抽取）", "layer": "R", "severity": "error"},
    "R6_REGULATORY_ACTION": {"label": "监管处罚", "desc": "R6：监管函 / 立案调查 / 重大处罚（AI 从 8-K 抽取）", "layer": "R", "severity": "error"},
    "R7_CUSTOMER_CONCENTRATION": {"label": "客户集中", "desc": "R7：年报披露 top1 客户 > 25% 或 top5 > 50%", "layer": "R", "severity": "warning"},
    "R8_SUPPLIER_CONCENTRATION": {"label": "供应商集中", "desc": "R8：年报披露 top1 供应商 > 25% 或 top5 > 50%", "layer": "R", "severity": "warning"},
    "R9_TURNAROUND_TRAP": {"label": "转型陷阱", "desc": "R9：5Y 历史差但近 1-2 年改善 + restructuring 叙事，多数最终回归均值", "layer": "R", "severity": "warning"},
    "R10_MANAGEMENT_INSTABILITY": {"label": "管理层不稳", "desc": "R10：CEO/CFO 3 年内更迭 ≥ 2 次（8-K Item 5.02 信号）", "layer": "R", "severity": "warning"},
    "R11_MINORITY_UNFRIENDLY": {"label": "少数股东风险", "desc": "R11：关联交易异常 / 资金占用 / 低价定增", "layer": "R", "severity": "warning"},
    "R12_DISRUPTION": {"label": "行业断裂", "desc": "R12：护城河被技术/监管颠覆（AI 判定）", "layer": "R", "severity": "warning"},
    "R_PASS": {"label": "R 通过", "desc": "R 层全部通过", "layer": "R", "severity": "info"},
    "R_RULE_ONLY": {"label": "仅规则", "desc": "R 层 AI 未启用或调用失败，仅基于硬规则结果", "layer": "R", "severity": "info"},

    # ============ V 价格层 ============
    "V1_NEGATIVE_EPS": {"label": "EPS≤0", "desc": "V1：净利润为负或 0，PE 无意义，不进入买入状态", "layer": "V", "severity": "warning"},
    "V2_PASS_STRICT": {"label": "PE 严格通过", "desc": "V2：PE_TTM ≤ 14.9（PRD 默认严格买入锚）", "layer": "V", "severity": "info"},
    "V3_PASS_STANDARD": {"label": "PE 标准通过", "desc": "V3：PE_TTM 在分级阈值内（顶级 ≤22 / 5Y通过 ≤18 / 其他 ≤15）", "layer": "V", "severity": "info"},
    "V_TOO_EXPENSIVE": {"label": "估值过高", "desc": "V：PE_TTM 超过当前模式上限，不进入候选", "layer": "V", "severity": "warning"},
    "V_NO_PRICE": {"label": "无价", "desc": "V：market_bar 无数据或 EPS≤0 致 PE 不可计算", "layer": "V", "severity": "warning"},

    # ============ AI 风险层标签 ============
    "AI_GOVERNANCE_RISK": {"label": "AI:治理风险", "desc": "AI 识别：董事会冲突 / 关联交易 / 控制权异常", "layer": "AI", "severity": "warning"},
    "AI_ACCOUNTING_RISK": {"label": "AI:会计问题", "desc": "AI 识别：非标审计 / 重大重述 / 会计政策激进", "layer": "AI", "severity": "error"},
    "AI_REGULATORY_RISK": {"label": "AI:监管风险", "desc": "AI 识别：立案调查 / 监管函 / 重大处罚", "layer": "AI", "severity": "error"},
    "AI_TURNAROUND_RISK": {"label": "AI:转型陷阱", "desc": "AI 识别：restructuring 叙事 + 5Y 历史差", "layer": "AI", "severity": "warning"},
    "AI_SERIAL_ACQUIRER_RISK": {"label": "AI:并购成瘾", "desc": "AI 识别：频繁并购 + ROCE 下滑", "layer": "AI", "severity": "warning"},
    "AI_CUSTOMER_CONCENTRATION_RISK": {"label": "AI:客户集中", "desc": "AI 识别：客户集中度风险（年报披露）", "layer": "AI", "severity": "warning"},
    "AI_SUPPLIER_CONCENTRATION_RISK": {"label": "AI:供应商集中", "desc": "AI 识别：供应商集中度风险", "layer": "AI", "severity": "warning"},
    "AI_DISRUPTION_RISK": {"label": "AI:行业断裂", "desc": "AI 识别：技术或监管颠覆护城河", "layer": "AI", "severity": "warning"},
    "AI_MINORITY_SHAREHOLDER_RISK": {"label": "AI:少数股东", "desc": "AI 识别：少数股东不友好行为", "layer": "AI", "severity": "warning"},
}


# 高严重度后缀（severity=high）
HIGH_SEVERITY_SUFFIX = "_HIGH"


def lookup(code: str) -> LabelEntry:
    """主入口：返回 reason_code 的中文 label。未注册的 code 返回兜底。"""
    if code in REASON_LABELS:
        return REASON_LABELS[code]

    # AI 标签可能附 _HIGH 后缀（来自 r_layer：AI_{LABEL}_HIGH）
    if code.endswith(HIGH_SEVERITY_SUFFIX):
        base = code[: -len(HIGH_SEVERITY_SUFFIX)]
        if base in REASON_LABELS:
            ent = dict(REASON_LABELS[base])
            ent["label"] = ent["label"] + "(高)"
            ent["severity"] = "error"
            return ent  # type: ignore[return-value]

    # 兜底：未注册 code
    return {
        "label": code,
        "desc": f"未注册的 reason_code: {code}",
        "layer": "META",
        "severity": "info",
    }


def all_labels() -> dict[str, LabelEntry]:
    """返回全部已注册映射（前端启动时拉一次）。"""
    return dict(REASON_LABELS)
