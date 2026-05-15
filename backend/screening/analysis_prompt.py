# -*- coding: utf-8 -*-
"""生成给 ChatGPT / Claude / Gemini 用户自助分析的中文 prompt（优化5）。

包含 Pulak Prasad 方法论介绍 + 公司基础信息 + 关键指标 + 漏斗判定结果 +
SEC 财报链接 + 8 个引导问题。用户复制后粘贴到 AI 工具，再附上财报 PDF，
即可获得深度分析。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.filing import Filing
from backend.models.metric_periodic import MetricPeriodic
from backend.models.screen_result import ScreenResult
from backend.screening.reason_labels import lookup


def _latest_metric(db, cid, name, fv) -> Optional[tuple[float, str]]:
    row = db.execute(
        select(MetricPeriodic.value, MetricPeriodic.period_end)
        .where(and_(
            MetricPeriodic.company_id == cid,
            MetricPeriodic.metric_name == name,
            MetricPeriodic.formula_version == fv,
            MetricPeriodic.value.isnot(None),
        ))
        .order_by(MetricPeriodic.period_end.desc())
        .limit(1)
    ).first()
    if row is None or row.value is None:
        return None
    return float(row.value), row.period_end.isoformat()


def _fmt(v: Optional[tuple[float, str]], suffix: str = "", scale: float = 1.0,
         decimals: int = 2) -> str:
    if v is None:
        return "暂无数据"
    val, period = v
    return f"{val * scale:.{decimals}f}{suffix} (财年末 {period})"


def _recent_filings(db, cid, limit: int = 3) -> list[tuple[str, str]]:
    """取最近 limit 个 10-K filing 的 (filed_date, url)。

    filing 表无 period_end，用 filed_date 作显示日期。
    """
    rows = db.execute(
        select(Filing.filed_date, Filing.url_pdf, Filing.url)
        .where(and_(
            Filing.company_id == cid,
            Filing.form_type == "10-K",
        ))
        .order_by(Filing.filed_date.desc())
        .limit(limit)
    ).all()
    out = []
    for r in rows:
        url = r.url_pdf or r.url
        if r.filed_date and url:
            out.append((r.filed_date.isoformat(), url))
    return out


def generate_analysis_prompt(
    db: Session, company_id: str, run_id: Optional[int] = None
) -> Optional[str]:
    """主入口。"""
    company = db.get(Company, company_id)
    if company is None:
        return None

    # 读关键指标
    roce_5y = _latest_metric(db, company_id, "roce_5y_median", "roce_v1")
    roce_10y = _latest_metric(db, company_id, "roce_10y_median", "roce_v1")
    q4 = _latest_metric(db, company_id, "q4_strong_track_record", "roce_v1")
    nd_ebit = _latest_metric(db, company_id, "net_debt_ebit", "leverage_v1")
    int_cov = _latest_metric(db, company_id, "interest_coverage", "leverage_v1")
    cur_ratio = _latest_metric(db, company_id, "current_ratio", "leverage_v1")
    cfo_ni = _latest_metric(db, company_id, "median_cfo_ni_5y", "cash_quality_v1")
    fcf_neg = _latest_metric(db, company_id, "fcf_neg_5y_years", "cash_quality_v1")
    share_cagr = _latest_metric(db, company_id, "share_count_cagr_5y", "dilution_v1")
    pe = _latest_metric(db, company_id, "pe_ttm", "valuation_v1")
    mc = _latest_metric(db, company_id, "market_cap", "valuation_v1")
    ev_ebit = _latest_metric(db, company_id, "ev_ebit", "valuation_v1")

    # 取漏斗判定（如有指定 run_id 用之，否则取该公司最新一次）
    sr = None
    if run_id is not None:
        sr = db.execute(
            select(ScreenResult).where(and_(
                ScreenResult.run_id == run_id,
                ScreenResult.company_id == company_id,
            )).limit(1)
        ).scalar()
    if sr is None:
        sr = db.execute(
            select(ScreenResult).where(ScreenResult.company_id == company_id)
            .order_by(ScreenResult.result_id.desc()).limit(1)
        ).scalar()

    status_str = sr.status if sr else "（未运行筛选）"
    r_action = sr.r_action if sr else "—"
    reason_codes = sr.reason_codes or [] if sr else []
    reason_codes_cn = [
        f"{c}({lookup(c)['label']})" for c in reason_codes[:10]
    ]

    # 最近 3 份 10-K
    recent_10k = _recent_filings(db, company_id, limit=3)
    filings_str = "\n".join(f"- {pe_date}: {url}" for pe_date, url in recent_10k) if recent_10k \
        else "（暂无 10-K 数据，可访问 SEC EDGAR 直接搜索）"

    market_label = "美股" if company.market == "US" else "A 股"
    ticker_or_code = company.cik or company.stock_code or company_id

    # 拼 prompt
    prompt = f"""你是一位严格遵循 Pulak Prasad《What I Learned About Investing from Darwin》(2023) 方法论的资深投资分析师。请按以下方法论框架对【{company.name}】（{market_label} · {ticker_or_code}）进行深度分析。

## 方法论框架

**三层漏斗筛选**：
1. **Q 层（质量门槛）**：5 年 ROCE 中位数 ≥ 20% 且 4/5 年 ROCE ≥ 20%（ROCE 严格口径：EBIT / (NetWorkingCapitalExcessCash + NetPPE)，剔除超额现金与商誉）
2. **R 层（风险过滤）**：审计/治理/监管/客户集中/管理层稳定/转型陷阱/并购成瘾等
3. **V 层（价格闸门）**：默认 PE_TTM ≤ 14.9 严格买入锚，标准模式分级 ≤ 18 / ≤ 22

**5 状态语义**：
- Rejected（排除）/ Review（人工覆核）/ TooExpensive（合格但太贵）/ NearFairPrice（近合理价）/ HighConviction（高确信）

**核心信条**：耐心持有质量公司、不追逐反转、不重仓周期股、严守安全边际。

---

## 公司基础信息

| 项 | 值 |
|---|---|
| 名称 | {company.name} |
| 市场 | {market_label} |
| 代码 | {ticker_or_code} |
| 行业 | {company.industry_name or '未分类'} |
| 证券类型 | {company.instrument_type} |
| 财年末月份 | {company.fiscal_year_end_month or '?'} 月 |

---

## 已计算的关键指标（截至最新可见财报）

### 质量层（Q）
- 5 年 ROCE 中位数：{_fmt(roce_5y, '%', 100, 1)}
- 10 年 ROCE 中位数：{_fmt(roce_10y, '%', 100, 1)}
- 10Y 强通过（Q4_STRONG_TRACK_RECORD）：{"通过" if (q4 and q4[0] >= 1) else "未通过"}

### 风险层（R）
- net_debt / EBIT：{_fmt(nd_ebit, '', 1.0, 2)}
- 利息保障倍数：{_fmt(int_cov, 'x', 1.0, 1)}
- 流动比：{_fmt(cur_ratio, '', 1.0, 2)}
- 5 年 CFO/NI 中位数：{_fmt(cfo_ni, '', 1.0, 2)}
- 5 年内 FCF 为负年数：{int(fcf_neg[0]) if fcf_neg else 0} / 5
- 5 年股本 CAGR：{_fmt(share_cagr, '%', 100, 2)}

### 价格层（V）
- 当前市值：{f'{mc[0]/1e9:.1f}B' if mc else '—'}
- PE_TTM：{_fmt(pe, 'x', 1.0, 1)}
- EV / EBIT：{_fmt(ev_ebit, 'x', 1.0, 1)}

---

## Darwen 系统判定

- **状态**：{status_str}
- **R 层动作**：{r_action}
- **触发原因码**：{', '.join(reason_codes_cn) if reason_codes_cn else '无'}

---

## 数据来源（SEC EDGAR 10-K，请在 AI 对话中附上财报 PDF 一起分析）

{filings_str}

---

## 请你完成的分析（用中文回答，每条要求引用具体证据）

1. **业务描述与护城河（Moat）**：用 3-5 句概括公司是做什么的、靠什么赚钱。识别其护城河类型（品牌 / 网络效应 / 转换成本 / 规模 / 监管牌照 / 无形资产），并指出 10-K 中支持的证据段落。

2. **客户集中度风险**：从 10-K Item 1A Risk Factors 或 Item 7 MD&A 抽取关于客户集中度的披露。是否有 top1 客户 > 25% 或 top5 > 50%？若有，识别为哪些客户。

3. **资本配置质量**：管理层如何使用经营现金流？分红、回购、并购、研发、CapEx 各占多少？是否高 ROIC 再投资？

4. **审计 / 治理 / 监管风险**：审计意见类型（是否非标），近 3 年是否有 SEC 监管函 / 集体诉讼 / 重大重述？是否存在治理结构异常（如双重投票权、控制权集中）？

5. **转型陷阱（Turnaround Trap）识别**：管理层叙事是否含"restructuring / pivot / refresh / new strategy"等字眼？历史 ROCE 趋势是否支持转型成功？根据 Pulak，多数转型最终失败。

6. **并购成瘾检查**：近 3 年是否有大额并购？商誉占总资产比例？并购后 ROCE 是否改善？

7. **估值合理性**：当前 PE 是否反映长期增长率？与历史中位数比较，与同业（举 2-3 家可比公司）比较。

8. **最终建议**：给出 1 个明确结论 — 进入买入候选 / 加观察名单 / 排除。理由必须基于上述 7 点的证据汇总，不得引入新信息。

---

**重要约束**：
- 不得引用未提供的数据
- 不得给出目标价位或买卖时机建议
- 所有结论必须能溯源到具体的 10-K 段落、财务数字或新闻事件
- 用中文输出，控制在 1500-2500 字
"""
    return prompt
