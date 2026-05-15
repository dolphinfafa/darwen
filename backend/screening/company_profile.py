# -*- coding: utf-8 -*-
"""公司画像规则化生成（优化3）。

从 metric_periodic 读最新指标，按 Pulak 方法论规则生成 5-12 条带数据依据的
中文观点（优势 / 隐忧 / 中性），每条引用具体指标值 + 财年。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.metric_periodic import MetricPeriodic


def _latest_metric(
    db: Session, company_id: str, metric_name: str, formula_version: str = "roce_v1"
) -> Optional[tuple[float, str]]:
    """读 ≤ 今天的最新 metric_periodic.value。返回 (value, period_end_str)。"""
    row = db.execute(
        select(MetricPeriodic.value, MetricPeriodic.period_end)
        .where(
            and_(
                MetricPeriodic.company_id == company_id,
                MetricPeriodic.metric_name == metric_name,
                MetricPeriodic.formula_version == formula_version,
                MetricPeriodic.value.isnot(None),
            )
        )
        .order_by(MetricPeriodic.period_end.desc())
        .limit(1)
    ).first()
    if row is None or row.value is None:
        return None
    return float(row.value), row.period_end.isoformat()


# 业务描述简表（按 instrument_type / industry_name 给一句话）
_INSTRUMENT_DESC = {
    "BANK": "商业银行业务，Pulak ROCE 严格口径不适用（资产负债结构特殊）",
    "INSURANCE": "保险公司，浮存金驱动业务，ROCE 公式不适用",
    "BROKER": "证券/经纪商，业务结构使 ROCE 公式不适用",
    "REIT": "房地产投资信托，主要靠分红再投资，ROCE 公式不适用",
    "ETF": "交易型开放式基金，非运营公司",
    "FUND": "投资基金",
    "SPAC": "特殊目的收购公司，无运营历史",
    "ADR": "美国存托凭证",
    "PREFERRED": "优先股",
    "WARRANT": "认股权证",
    "SHELL": "壳公司",
}


def generate_profile(db: Session, company_id: str) -> Optional[dict]:
    """主入口。生成画像 dict（含 strengths/concerns/neutral 数组）。"""
    company = db.get(Company, company_id)
    if company is None:
        return None

    # 业务描述
    inst_desc = _INSTRUMENT_DESC.get(company.instrument_type, "")
    parts = [company.market, company.industry_name or "（行业未分类）"]
    if inst_desc:
        parts.append(inst_desc)
    business_summary = " · ".join(p for p in parts if p)

    strengths: list[dict] = []
    concerns: list[dict] = []
    neutral: list[dict] = []

    # 读所有截面指标
    def read(name: str, fv: str = "roce_v1"):
        return _latest_metric(db, company_id, name, fv)

    roce_5y = read("roce_5y_median", "roce_v1")
    roce_10y = read("roce_10y_median", "roce_v1")
    q4_strong = read("q4_strong_track_record", "roce_v1")
    nd_ebit = read("net_debt_ebit", "leverage_v1")
    int_cov = read("interest_coverage", "leverage_v1")
    cur_ratio = read("current_ratio", "leverage_v1")
    net_debt = read("net_debt", "leverage_v1")
    med_cfo_ni = read("median_cfo_ni_5y", "cash_quality_v1")
    cfo_ni_below_07 = read("cfo_ni_5y_below_07_years", "cash_quality_v1")
    fcf_neg = read("fcf_neg_5y_years", "cash_quality_v1")
    share_cagr = read("share_count_cagr_5y", "dilution_v1")
    pe_ttm = read("pe_ttm", "valuation_v1")
    ev_ebit = read("ev_ebit", "valuation_v1")

    # ========= 优势 =========
    if roce_5y and roce_5y[0] > 0.30:
        strengths.append({
            "category": "strength",
            "title": "资本回报极优",
            "desc": f"5 年 ROCE 中位数 {roce_5y[0]*100:.1f}%，远超 PRD 默认门槛 20%，属顶级公司",
            "metric": "roce_5y_median", "value": f"{roce_5y[0]*100:.1f}%", "period": roce_5y[1],
        })
    elif roce_5y and roce_5y[0] >= 0.20:
        strengths.append({
            "category": "strength",
            "title": "资本回报达标",
            "desc": f"5 年 ROCE 中位数 {roce_5y[0]*100:.1f}%，满足 Pulak 20% 门槛",
            "metric": "roce_5y_median", "value": f"{roce_5y[0]*100:.1f}%", "period": roce_5y[1],
        })

    if q4_strong and q4_strong[0] >= 1.0:
        strengths.append({
            "category": "strength",
            "title": "10 年强 track record",
            "desc": "近 10 年中至少 8 年 ROCE ≥ 20%，符合 Pulak 强通过标准（PRD Q4）",
            "metric": "q4_strong_track_record", "value": "通过", "period": q4_strong[1],
        })

    if med_cfo_ni and med_cfo_ni[0] > 1.0:
        strengths.append({
            "category": "strength",
            "title": "现金流质量优秀",
            "desc": f"5 年 CFO/NI 中位数 {med_cfo_ni[0]:.2f}，经营现金流持续高于会计利润，盈利可靠",
            "metric": "median_cfo_ni_5y", "value": f"{med_cfo_ni[0]:.2f}", "period": med_cfo_ni[1],
        })

    if share_cagr and share_cagr[0] < -0.01:
        strengths.append({
            "category": "strength",
            "title": "持续回购股本",
            "desc": f"5 年股本年化变化 {share_cagr[0]*100:+.2f}%（缩股），股东友好的资本回报",
            "metric": "share_count_cagr_5y", "value": f"{share_cagr[0]*100:+.2f}%", "period": share_cagr[1],
        })

    if net_debt and net_debt[0] < 0:
        strengths.append({
            "category": "strength",
            "title": "净现金状态",
            "desc": f"净债务为负（净现金 {-net_debt[0]/1e9:.1f}B），财务弹性极强，不受利率周期影响",
            "metric": "net_debt", "value": f"{net_debt[0]/1e9:.1f}B", "period": net_debt[1],
        })

    if int_cov and int_cov[0] > 20:
        strengths.append({
            "category": "strength",
            "title": "利息保障极高",
            "desc": f"利息保障倍数 {int_cov[0]:.0f}x，财务安全边际充足",
            "metric": "interest_coverage", "value": f"{int_cov[0]:.0f}x", "period": int_cov[1],
        })

    # ========= 隐忧 =========
    if nd_ebit and nd_ebit[0] > 4:
        concerns.append({
            "category": "concern",
            "title": "杠杆较高",
            "desc": f"net_debt/EBIT = {nd_ebit[0]:.2f}x，超过 PRD 标准模式阈值 4x，去杠杆压力或带来现金流挤压",
            "metric": "net_debt_ebit", "value": f"{nd_ebit[0]:.2f}x", "period": nd_ebit[1],
        })

    if int_cov is not None and 0 < int_cov[0] < 3:
        concerns.append({
            "category": "concern",
            "title": "利息保障偏低",
            "desc": f"利息保障倍数仅 {int_cov[0]:.2f}x（< PRD 标准 3x），盈利下行时偿债压力大",
            "metric": "interest_coverage", "value": f"{int_cov[0]:.2f}x", "period": int_cov[1],
        })
    elif int_cov is not None and int_cov[0] < 0:
        concerns.append({
            "category": "concern",
            "title": "EBIT 为负",
            "desc": f"利息保障倍数为负数（{int_cov[0]:.1f}x），公司当前经营亏损，无法靠自身利润覆盖利息",
            "metric": "interest_coverage", "value": f"{int_cov[0]:.1f}x", "period": int_cov[1],
        })

    if cur_ratio and cur_ratio[0] < 1.0:
        concerns.append({
            "category": "concern",
            "title": "短期流动性紧张",
            "desc": f"流动比 {cur_ratio[0]:.2f} < 1，流动资产不足以覆盖流动负债，依赖外部续命或营运高效",
            "metric": "current_ratio", "value": f"{cur_ratio[0]:.2f}", "period": cur_ratio[1],
        })

    if fcf_neg and fcf_neg[0] >= 3:
        concerns.append({
            "category": "concern",
            "title": "FCF 长期为负",
            "desc": f"近 5 年内有 {int(fcf_neg[0])} 年自由现金流为负，持续烧钱或处于重资本扩张期",
            "metric": "fcf_neg_5y_years", "value": f"{int(fcf_neg[0])}/5", "period": fcf_neg[1],
        })

    if cfo_ni_below_07 and cfo_ni_below_07[0] >= 2:
        concerns.append({
            "category": "concern",
            "title": "盈利质量存疑",
            "desc": f"近 5 年有 {int(cfo_ni_below_07[0])} 年 CFO/NI < 0.7，会计利润未充分转化为现金（可能为应计项操纵或回款慢）",
            "metric": "cfo_ni_5y_below_07_years", "value": f"{int(cfo_ni_below_07[0])}/5", "period": cfo_ni_below_07[1],
        })

    if share_cagr and share_cagr[0] > 0.03:
        concerns.append({
            "category": "concern",
            "title": "股本持续稀释",
            "desc": f"5 年股本年化增长 {share_cagr[0]*100:+.2f}%（> PRD 标准 3%），若 ROCE 未同步改善则属高频稀释",
            "metric": "share_count_cagr_5y", "value": f"{share_cagr[0]*100:+.2f}%", "period": share_cagr[1],
        })

    if pe_ttm and pe_ttm[0] > 30:
        concerns.append({
            "category": "concern",
            "title": "估值偏贵",
            "desc": f"PE_TTM = {pe_ttm[0]:.1f}x，显著高于 PRD 标准模式上限 22x，安全边际不足",
            "metric": "pe_ttm", "value": f"{pe_ttm[0]:.1f}x", "period": pe_ttm[1],
        })

    # ========= 中性 =========
    if pe_ttm and 14.9 < pe_ttm[0] <= 22:
        neutral.append({
            "category": "neutral",
            "title": "估值合理偏贵",
            "desc": f"PE_TTM {pe_ttm[0]:.1f}x，处于 PRD 标准模式可接受区间（14.9-22）",
            "metric": "pe_ttm", "value": f"{pe_ttm[0]:.1f}x", "period": pe_ttm[1],
        })
    elif pe_ttm and pe_ttm[0] <= 14.9 and pe_ttm[0] > 0:
        neutral.append({
            "category": "neutral",
            "title": "估值便宜",
            "desc": f"PE_TTM {pe_ttm[0]:.1f}x，达 PRD 严格模式 14.9x 买入锚",
            "metric": "pe_ttm", "value": f"{pe_ttm[0]:.1f}x", "period": pe_ttm[1],
        })

    if ev_ebit and ev_ebit[0] > 0:
        neutral.append({
            "category": "neutral",
            "title": "EV/EBIT 参考",
            "desc": f"企业价值倍数 {ev_ebit[0]:.1f}x（与 PE 互补，剔除资本结构差异）",
            "metric": "ev_ebit", "value": f"{ev_ebit[0]:.1f}x", "period": ev_ebit[1],
        })

    if inst_desc:
        neutral.append({
            "category": "neutral",
            "title": f"{company.instrument_type} 类型",
            "desc": inst_desc,
        })

    if roce_10y and roce_5y and roce_10y[0] > roce_5y[0] * 1.15:
        neutral.append({
            "category": "neutral",
            "title": "近 5 年 ROCE 较 10 年趋势下行",
            "desc": f"10 年 ROCE 中位 {roce_10y[0]*100:.1f}% vs 5 年 {roce_5y[0]*100:.1f}%，竞争力或被挑战",
            "metric": "roce_5y vs 10y", "value": f"{roce_5y[0]*100:.1f}% vs {roce_10y[0]*100:.1f}%", "period": roce_5y[1],
        })

    return {
        "company_id": company_id,
        "name": company.name,
        "market": company.market,
        "industry_name": company.industry_name,
        "instrument_type": company.instrument_type,
        "business_summary": business_summary,
        "strengths": strengths[:6],   # 最多 6 条
        "concerns": concerns[:6],
        "neutral": neutral[:6],
    }
