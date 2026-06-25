# -*- coding: utf-8 -*-
"""三层漏斗引擎 v2：ROCE → 稳健性 → 风险性，分层执行 + 人工 gate。

与旧 funnel.py（Q/R/V + 估值）的区别：
- 去掉估值层；三层为 ROCE(规则) → 稳健性(规则+AI) → 风险性(AI)。
- 分层执行：每层跑完默认停在 awaiting_review 等人工放行/剔除，再 advance 下一层
  （run.auto_advance=True 时三层连跑）。
- 存活集语义：screen_result.rejected_at_layer IS NULL 即"当前存活/最终入选"；
  某层把不通过的公司标记 rejected_at_layer=该层。人工 force_pass 复活(置 NULL)、
  force_reject 出局(置当前层)。每层只处理存活集，计数自然守恒。

阶段说明：稳健层目前仅实现"无负债有充裕现金流"这一条可量化规则，其余 5 条稳健原则
与整个风险层标记为 pending_ai，由阶段 3 接入 AI 判定后真正过滤（pending 不影响存活）。
"""
from __future__ import annotations

import logging
from dataclasses import fields as dataclass_fields
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.governance_signal import GovernanceSignal
from backend.models.screen_result import ScreenResult
from backend.models.screen_run import ScreenRun

from backend.screening.config import ScreenConfig
from backend.screening.exclusion import evaluate_q0
from backend.screening.q_layer import evaluate_q_layer
from backend.screening.r_layer import _latest_section

log = logging.getLogger(__name__)

# 漏斗层顺序
LAYERS: tuple[str, ...] = ("roce", "sturdiness", "risk")
_NEXT: dict[str, str] = {"roce": "sturdiness", "sturdiness": "risk", "risk": "done"}

# 稳健层 reason codes（阶段2 规则部分）
STURDINESS_PASS = "STURDINESS_PASS"
STURDINESS_HIGH_DEBT = "STURDINESS_HIGH_DEBT"
STURDINESS_WEAK_COVERAGE = "STURDINESS_WEAK_COVERAGE"
STURDINESS_NEGATIVE_FCF = "STURDINESS_NEGATIVE_FCF"
# 财务风险扩展 hard（risk_v1：应计利润率 / FCF 波动）
STURDINESS_HIGH_ACCRUALS = "STURDINESS_HIGH_ACCRUALS"
STURDINESS_VOLATILE_FCF = "STURDINESS_VOLATILE_FCF"
# 软警告（soft：进入观察区不出局；叠加 ≥ config 阈值升级 hard）
STURDINESS_WATCH_DEBT = "STURDINESS_WATCH_DEBT"
STURDINESS_WATCH_COVERAGE = "STURDINESS_WATCH_COVERAGE"
STURDINESS_WATCH_FCF = "STURDINESS_WATCH_FCF"
STURDINESS_WATCH_ACCRUALS = "STURDINESS_WATCH_ACCRUALS"
STURDINESS_WATCH_FCF_VOL = "STURDINESS_WATCH_FCF_VOL"
STURDINESS_SOFT_STACK = "STURDINESS_SOFT_STACK"
# 偿付/营运资本扩展（solvency_v1：Altman Z / 营运资本增长领先 / CCC）
STURDINESS_DISTRESS_RISK = "STURDINESS_DISTRESS_RISK"
STURDINESS_WATCH_DISTRESS = "STURDINESS_WATCH_DISTRESS"
STURDINESS_WC_GROWTH_LEAD = "STURDINESS_WC_GROWTH_LEAD"
STURDINESS_WATCH_WC_GROWTH = "STURDINESS_WATCH_WC_GROWTH"
STURDINESS_CCC_DETERIORATING = "STURDINESS_CCC_DETERIORATING"
STURDINESS_WATCH_CCC = "STURDINESS_WATCH_CCC"
# 行业 peer 自建对标（industry_v1：营收增速相对同行业）
STURDINESS_INDUSTRY_LAGGARD = "STURDINESS_INDUSTRY_LAGGARD"
STURDINESS_WATCH_INDUSTRY = "STURDINESS_WATCH_INDUSTRY"
# 商业深度（commercial_v1：客户/供应商集中度 + segment HHI，从 10-K 抽取）
STURDINESS_CUSTOMER_CONCENTRATION = "STURDINESS_CUSTOMER_CONCENTRATION"
STURDINESS_WATCH_CUSTOMER = "STURDINESS_WATCH_CUSTOMER"
STURDINESS_SEGMENT_CONCENTRATION = "STURDINESS_SEGMENT_CONCENTRATION"
STURDINESS_WATCH_SEGMENT = "STURDINESS_WATCH_SEGMENT"
STURDINESS_SUPPLIER_CONCENTRATION = "STURDINESS_SUPPLIER_CONCENTRATION"
# 风险层占位（阶段3 接 AI）
RISK_PENDING_AI = "RISK_PENDING_AI"
# 风险层治理硬事实（solvency 之外的第三层；source=governance_signal）
RISK_RESTATEMENT = "RISK_RESTATEMENT"
RISK_AUDITOR_CHANGE = "RISK_AUDITOR_CHANGE"
RISK_MGMT_INSTABILITY_HARD = "RISK_MGMT_INSTABILITY_HARD"
RISK_MGMT_INSTABILITY_SOFT = "RISK_MGMT_INSTABILITY_SOFT"
RISK_HIGH_PLEDGE = "RISK_HIGH_PLEDGE"
RISK_WATCH_PLEDGE = "RISK_WATCH_PLEDGE"
RISK_GOV_PASS = "RISK_GOV_PASS"
# AI 判定 REVIEW（有风险但非法定确凿）→ 出局兜底标记（具体风险通常见 AI_* 标签）
STURDINESS_AI_FLAGGED = "STURDINESS_AI_REVIEW"
RISK_AI_FLAGGED = "RISK_AI_REVIEW"

# 稳健性 6 原则 key（前端展示用；阶段2 仅第 1 条有规则判定）
_STURDINESS_PRINCIPLES = (
    "no_debt_strong_cashflow",   # 无负债、有充裕现金流（规则）
    "diversified_customers",     # 多元化客户（AI）
    "high_moat",                 # 竞争壁垒高（ROCE 代理 + AI）
    "diversified_suppliers",     # 多元化供应商（AI）
    "stable_management",         # 稳定管理团队（AI）
    "slow_changing_industry",   # 行业变化慢（AI）
)


# ---------------- 配置/状态 helpers ----------------

def _config_from_run(run: ScreenRun) -> ScreenConfig:
    """从 run.config_snapshot 重建 ScreenConfig（仅取匹配字段，缺失用默认）。"""
    snap = dict(run.config_snapshot or {})
    valid = {f.name for f in dataclass_fields(ScreenConfig)}
    return ScreenConfig(**{k: v for k, v in snap.items() if k in valid})


def _set_run(db: Session, run_id: int, **values) -> None:
    """独立 UPDATE 刷新 screen_run 字段并 commit（避免与逐行 add 冲突）。"""
    db.execute(update(ScreenRun).where(ScreenRun.run_id == run_id).values(**values))
    db.commit()


def _recount(db: Session, run_id: int) -> tuple[int, int]:
    """重新统计存活/出局并写回 run。返回 (alive, rejected)。"""
    rows = db.execute(
        select(ScreenResult.rejected_at_layer).where(ScreenResult.run_id == run_id)
    ).all()
    alive = sum(1 for r in rows if r.rejected_at_layer is None)
    rejected = sum(1 for r in rows if r.rejected_at_layer is not None)
    _set_run(db, run_id, passed_count=alive, rejected_count=rejected)
    return alive, rejected


# ---------------- 各层评估（纯判定，返回 (alive, layer_result, status_hint)）----------------

def _eval_roce(db: Session, company: Company, asof: date, config: ScreenConfig) -> tuple[bool, dict, str]:
    """ROCE 层：Q0 排除 + ROCE 门槛（按 config.roce_lookback_years）。"""
    q0 = evaluate_q0(company)
    if q0 is not None:
        return False, {"passed": False, "reason_codes": [q0], "metrics": {}}, "Rejected"

    q = evaluate_q_layer(db, company, asof, config)
    passed = bool(q["q_passed"])
    result = {
        "passed": passed,
        "reason_codes": list(q["reason_codes"]),
        "metrics": {k: v for k, v in (q.get("metrics") or {}).items() if v is not None},
        "q_strong_track": bool(q["q_strong_track"]),
    }
    # Q5（负资本/缺失）属"需人工覆核"，状态标 Review 但仍按未通过过滤
    status = "Review" if any(c.startswith("Q5") for c in q["reason_codes"]) else (
        "HighConviction" if passed else "Rejected"
    )
    return passed, result, status


# AI 标签 → 稳健性原则 key（AI 判定后更新 principle 状态）
_STURDINESS_LABEL_TO_PRINCIPLE = {
    "customer_concentration_risk": "diversified_customers",
    "supplier_concentration_risk": "diversified_suppliers",
    "disruption_risk": "slow_changing_industry",
    "management_instability": "stable_management",
}


def _run_layer_ai(db: Session, company_id: str, asof: date, config: ScreenConfig,
                  user_id: Optional[int], run_id: Optional[int], layer: str):
    """调某层 AI 判定。返回 (ai_action, ai_result_id, ai_codes, labels)；
    未启用 AI / 未绑 key / 调用降级 → (None, None, [], [])。"""
    if not (config.ai_enabled_for(layer) and user_id is not None):
        return None, None, [], []
    from backend.ai.orchestrator import analyze_layer, AIResult
    # 用独立 session 调 AI：AI 内部的 commit/异常不污染漏斗主 session（否则整层 run_from 会抛错卡 running）
    ai_db = SessionLocal()
    try:
        outcome = analyze_layer(
            ai_db, company_id=company_id, asof_date=asof, user_id=user_id,
            run_id=run_id, layer=layer, rule_triggered={},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("AI %s layer failed for %s: %s", layer, company_id, e)
        return None, None, [], []
    finally:
        ai_db.close()
    if not isinstance(outcome, AIResult):
        return None, None, [], []  # RuleOnly 降级
    codes = [
        f"AI_{lbl.label.upper()}" + ("_HIGH" if lbl.severity == "high" else "")
        for lbl in outcome.output.labels
    ]
    return outcome.overall_action, outcome.ai_result_id, codes, outcome.output.labels


def _has_supplier_concentration(db: Session, company_id: str, asof: date) -> bool:
    """点时查 governance_signal 是否有供应商集中度软旗标（SEC-10K，commercial_v1）。"""
    row = db.execute(
        select(GovernanceSignal.signal_id)
        .where(GovernanceSignal.company_id == company_id)
        .where(GovernanceSignal.signal_type == "supplier_concentration")
        .where(GovernanceSignal.event_date <= asof)
        .limit(1)
    ).first()
    return row is not None


def _eval_sturdiness(db: Session, company_id: str, asof: date, config: ScreenConfig,
                     user_id: Optional[int], run_id: Optional[int]) -> tuple[bool, dict]:
    """稳健层：可量化规则（含商业深度硬事实）+ 其余原则 AI 判定（启用 AI 时）。"""
    reason_codes: list[str] = []
    soft_codes: list[str] = []
    metrics: dict[str, float] = {}
    nd_ebit = _latest_section(db, company_id, "net_debt_ebit", "leverage_v1", asof)
    int_cov = _latest_section(db, company_id, "interest_coverage", "leverage_v1", asof)
    fcf_neg = _latest_section(db, company_id, "fcf_neg_5y_years", "cash_quality_v1", asof)
    accruals = _latest_section(db, company_id, "accruals_3y_avg", "risk_v1", asof)
    fcf_cv = _latest_section(db, company_id, "fcf_cv_5y", "risk_v1", asof)
    altman_z = _latest_section(db, company_id, "altman_z_latest", "solvency_v1", asof)
    ar_lead = _latest_section(db, company_id, "ar_lead_3y", "solvency_v1", asof)
    inv_lead = _latest_section(db, company_id, "inv_lead_3y", "solvency_v1", asof)
    ccc_delta = _latest_section(db, company_id, "ccc_delta_3y", "solvency_v1", asof)
    rev_vs_ind = _latest_section(db, company_id, "rev_growth_vs_industry", "industry_v1", asof)
    # 商业深度（commercial_v1：客户集中度 / segment 收入 HHI，从 10-K 抽取）
    cust_pct = _latest_section(db, company_id, "top_customer_revenue_pct", "commercial_v1", asof)
    seg_hhi = _latest_section(db, company_id, "segment_revenue_hhi", "commercial_v1", asof)
    supplier_flag = _has_supplier_concentration(db, company_id, asof)
    # 营运资本增长领先取应收/存货中较激进者
    wc_lead = None
    if ar_lead is not None or inv_lead is not None:
        wc_lead = max(v for v in (ar_lead, inv_lead) if v is not None)
    hard_fail = False

    def _grade(name, value, soft_t, hard_t, hard_code, soft_code, *, higher_worse=True):
        """三档判定：达 hard 阈 → 记 hard_code + 标 hard_fail；介于 soft~hard → 记 soft_code（观察区，不出局）。"""
        nonlocal hard_fail
        if value is None:
            return
        metrics[name] = value
        bad_hard = value > hard_t if higher_worse else value < hard_t
        bad_soft = value > soft_t if higher_worse else value < soft_t
        if bad_hard:
            reason_codes.append(hard_code); hard_fail = True
        elif bad_soft:
            soft_codes.append(soft_code)

    # 杠杆 / 偿债 / 现金流（leverage_v1 + cash_quality_v1）
    _grade("net_debt_ebit", nd_ebit, config.r1_net_debt_ebit_soft, config.r1_net_debt_ebit_max,
           STURDINESS_HIGH_DEBT, STURDINESS_WATCH_DEBT)
    _grade("interest_coverage", int_cov, config.r1_interest_coverage_soft, config.r1_interest_coverage_min,
           STURDINESS_WEAK_COVERAGE, STURDINESS_WATCH_COVERAGE, higher_worse=False)
    _grade("fcf_neg_5y_years", fcf_neg, config.r2_fcf_neg_5y_soft, config.r2_fcf_neg_5y_max,
           STURDINESS_NEGATIVE_FCF, STURDINESS_WATCH_FCF)
    # 财务风险扩展（risk_v1）：应计利润率 / FCF 波动
    _grade("accruals_3y_avg", accruals, config.r_accruals_3y_soft, config.r_accruals_3y_hard,
           STURDINESS_HIGH_ACCRUALS, STURDINESS_WATCH_ACCRUALS)
    _grade("fcf_cv_5y", fcf_cv, config.r_fcf_cv_5y_soft, config.r_fcf_cv_5y_hard,
           STURDINESS_VOLATILE_FCF, STURDINESS_WATCH_FCF_VOL)
    # 偿付/营运资本（solvency_v1）：Altman Z 越低越差；营运资本增长领先 / CCC 恶化 越高越差
    _grade("altman_z_latest", altman_z, config.r_altman_z_soft, config.r_altman_z_hard,
           STURDINESS_DISTRESS_RISK, STURDINESS_WATCH_DISTRESS, higher_worse=False)
    _grade("wc_growth_lead", wc_lead, config.r_wc_growth_lead_soft, config.r_wc_growth_lead_hard,
           STURDINESS_WC_GROWTH_LEAD, STURDINESS_WATCH_WC_GROWTH)
    _grade("ccc_delta_3y", ccc_delta, config.r_ccc_delta_soft, config.r_ccc_delta_hard,
           STURDINESS_CCC_DETERIORATING, STURDINESS_WATCH_CCC)
    # 行业 peer：营收增速显著落后同行业（越低越差，soft 为主、极端才 hard）
    _grade("rev_growth_vs_industry", rev_vs_ind, config.r_rev_lag_industry_soft, config.r_rev_lag_industry_hard,
           STURDINESS_INDUSTRY_LAGGARD, STURDINESS_WATCH_INDUSTRY, higher_worse=False)
    # 商业深度（commercial_v1）：客户集中度 / segment HHI 越高越差，soft 为主、hard 设深
    _grade("top_customer_revenue_pct", cust_pct, config.r_customer_concentration_soft,
           config.r_customer_concentration_hard, STURDINESS_CUSTOMER_CONCENTRATION, STURDINESS_WATCH_CUSTOMER)
    _grade("segment_revenue_hhi", seg_hhi, config.r_segment_hhi_soft, config.r_segment_hhi_hard,
           STURDINESS_SEGMENT_CONCENTRATION, STURDINESS_WATCH_SEGMENT)
    # 供应商集中度：10-K 定性旗标，仅 soft（计入软警告叠加，不单独硬剔除）
    if supplier_flag:
        soft_codes.append(STURDINESS_SUPPLIER_CONCENTRATION)

    # 软警告叠加升级：≥ 阈值视为结构性脆弱 → 升级硬剔除
    if len(soft_codes) >= config.r_soft_stack_to_hard:
        hard_fail = True
        reason_codes.append(STURDINESS_SOFT_STACK)
    reason_codes.extend(soft_codes)
    rule_fail = hard_fail

    # 商业深度硬事实优先：有 10-K 数据时，两条商业原则按规则判定（覆盖 AI 占位）
    commercial_principles: dict[str, dict] = {}
    if cust_pct is not None:
        cust_status = ("fail" if STURDINESS_CUSTOMER_CONCENTRATION in reason_codes
                       else "watch" if STURDINESS_WATCH_CUSTOMER in soft_codes else "pass")
        commercial_principles["diversified_customers"] = {
            "status": cust_status, "method": "rule",
            "metrics": {"top_customer_revenue_pct": cust_pct}}
    if supplier_flag:
        commercial_principles["diversified_suppliers"] = {
            "status": "watch", "method": "rule",
            "reason": "10-K 披露依赖单一/有限供应商（sole/limited source）"}

    principles = {
        "no_debt_strong_cashflow": {"status": "fail" if rule_fail else "pass",
                                    "method": "rule", "metrics": metrics},
    }

    ai_action, ai_id, ai_codes, labels = _run_layer_ai(
        db, company_id, asof, config, user_id, run_id, "sturdiness")
    reason_codes.extend(ai_codes)
    pending = ai_action is None
    if pending:
        for p in _STURDINESS_PRINCIPLES[1:]:
            principles[p] = {"status": "pending_ai", "method": "ai"}
    else:
        flagged: dict[str, dict] = {}
        for lbl in labels:
            pk = _STURDINESS_LABEL_TO_PRINCIPLE.get(lbl.label)
            if pk:
                flagged[pk] = {"status": "fail", "method": "ai", "severity": lbl.severity,
                               "reason": lbl.short_reason, "evidence_doc_ids": lbl.evidence_doc_ids}
        for p in _STURDINESS_PRINCIPLES[1:]:
            principles[p] = flagged.get(p, {"status": "pass", "method": "ai"})

    # 硬事实优先：商业深度规则判定覆盖 AI/占位（diversified_customers / diversified_suppliers）
    principles.update(commercial_principles)

    # REVIEW/REJECT 出局；PASS 与 MONITOR（"有轻微迹象但不阻止"）通过；None=未跑 AI 不出局
    ai_blocked = ai_action in ("REVIEW", "REJECT")
    passed = (not rule_fail) and not ai_blocked
    if ai_blocked and not any(c.startswith("AI_") for c in reason_codes):
        reason_codes.append(STURDINESS_AI_FLAGGED)
    if passed and not reason_codes:
        reason_codes.append(STURDINESS_PASS)
    return passed, {
        "passed": passed, "reason_codes": reason_codes, "metrics": metrics,
        "principles": principles, "pending_ai": pending,
        "ai_result_id": ai_id, "ai_action": ai_action,
    }


def _eval_governance_facts(db: Session, company_id: str, asof: date,
                           config: ScreenConfig) -> tuple[bool, list[str], dict]:
    """治理硬事实（governance_signal，点时 event_date ≤ asof）。

    返回 (hard_fail, codes, metrics)。硬事实优先于 AI：命中即出局，AI 未启用时仍生效。
    - restatement(4.02) → hard 直接出局
    - exec_departure(5.02) 近 3 年计数 ≥ hard 阈 → hard；≥ soft 阈 → soft
    - auditor_change(4.01) → soft（记录不出局）
    """
    codes: list[str] = []
    metrics: dict[str, float] = {}
    hard_fail = False
    three_y_ago = date(asof.year - 3, asof.month, asof.day)

    rows = db.execute(
        select(GovernanceSignal.signal_type, GovernanceSignal.event_date, GovernanceSignal.value)
        .where(GovernanceSignal.company_id == company_id)
        .where(GovernanceSignal.event_date <= asof)
    ).all()

    has_restatement = any(t == "restatement" for t, _, _ in rows)
    has_auditor_change = any(t == "auditor_change" for t, _, _ in rows)
    exec_dep_3y = sum(1 for t, ed, _ in rows if t == "exec_departure" and ed >= three_y_ago)
    # 股权质押：取 ≤ as_of 最新一期快照
    pledge = sorted(
        ((ed, v) for t, ed, v in rows if t == "share_pledge" and v is not None),
        key=lambda x: x[0],
    )

    if has_restatement:
        codes.append(RISK_RESTATEMENT); hard_fail = True
    if has_auditor_change:
        codes.append(RISK_AUDITOR_CHANGE)
    if exec_dep_3y:
        metrics["exec_departure_3y"] = float(exec_dep_3y)
        if exec_dep_3y >= config.risk_exec_departure_3y_hard:
            codes.append(RISK_MGMT_INSTABILITY_HARD); hard_fail = True
        elif exec_dep_3y >= config.risk_exec_departure_3y_soft:
            codes.append(RISK_MGMT_INSTABILITY_SOFT)
    if pledge:
        ratio = pledge[-1][1]
        metrics["pledge_ratio"] = ratio
        if ratio >= config.risk_pledge_ratio_hard:
            codes.append(RISK_HIGH_PLEDGE); hard_fail = True
        elif ratio >= config.risk_pledge_ratio_soft:
            codes.append(RISK_WATCH_PLEDGE)

    return hard_fail, codes, metrics


def _eval_risk(db: Session, company_id: str, asof: date, config: ScreenConfig,
               user_id: Optional[int], run_id: Optional[int]) -> tuple[bool, dict]:
    """风险层：治理硬事实（governance_signal）优先 + AI 判定佐证。

    硬事实（财务重述 / 管理层剧烈动荡）命中即出局，AI 未启用时仍生效；
    soft 信号记录但不单独出局；其余交 AI（5 条风险原则）综合。"""
    gov_hard, gov_codes, gov_metrics = _eval_governance_facts(db, company_id, asof, config)

    ai_action, ai_id, ai_codes, labels = _run_layer_ai(
        db, company_id, asof, config, user_id, run_id, "risk")

    codes = list(gov_codes)
    if ai_action is None:
        # AI 未启用：仅靠治理硬事实判定；无硬事实则占位放行
        if gov_hard:
            return False, {"passed": False, "reason_codes": codes, "metrics": gov_metrics,
                           "pending_ai": False, "ai_result_id": None, "ai_action": None}
        if not codes:
            codes.append(RISK_PENDING_AI)
        return True, {"passed": True, "reason_codes": codes, "metrics": gov_metrics,
                      "pending_ai": True, "ai_result_id": None, "ai_action": None}

    # AI 已跑：硬事实 OR AI REVIEW/REJECT → 出局
    ai_blocked = ai_action in ("REVIEW", "REJECT")
    codes.extend(ai_codes)
    passed = (not gov_hard) and (not ai_blocked)
    if ai_blocked and not any(c.startswith("AI_") for c in ai_codes):
        codes.append(RISK_AI_FLAGGED)
    if passed and not codes:
        codes.append(RISK_GOV_PASS)
    return passed, {"passed": passed, "reason_codes": codes, "metrics": gov_metrics,
                    "pending_ai": False, "ai_result_id": ai_id, "ai_action": ai_action}


_LAYER_EVAL = {
    "sturdiness": _eval_sturdiness,
    "risk": _eval_risk,
}


# ---------------- 分层执行 ----------------

def _alive_company_ids(db: Session, run_id: int) -> list[str]:
    """当前存活集：rejected_at_layer IS NULL 的 result（按 result_id 稳定排序）。"""
    rows = db.execute(
        select(ScreenResult.company_id)
        .where(ScreenResult.run_id == run_id, ScreenResult.rejected_at_layer.is_(None))
        .order_by(ScreenResult.result_id)
    ).all()
    return [r.company_id for r in rows]


def _run_roce_layer(db: Session, run: ScreenRun, config: ScreenConfig) -> None:
    """ROCE 层：对全 universe 建 screen_result 行。"""
    universe = list(run.universe_snapshot or [])
    _set_run(db, run.run_id, current_layer="roce", layer_status="running",
             progress_count=0, total_count=len(universe), current_company_name=None)

    for idx, cid in enumerate(universe, 1):
        company = db.get(Company, cid)
        if company is None:
            _set_run(db, run.run_id, progress_count=idx)
            continue
        try:
            alive, layer_res, status = _eval_roce(db, company, run.as_of_date, config)
            row = ScreenResult(
                run_id=run.run_id,
                company_id=cid,
                status=status,
                q_passed=layer_res.get("passed", False),
                q_strong_track=layer_res.get("q_strong_track", False),
                reason_codes=list(layer_res.get("reason_codes") or []),
                metrics_snapshot=dict(layer_res.get("metrics") or {}),
                layer_results={"roce": layer_res},
                rejected_at_layer=None if alive else "roce",
            )
            db.add(row)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.exception("roce layer failed for %s: %s", cid, e)
        _set_run(db, run.run_id, progress_count=idx, current_company_name=company.name)

    _recount(db, run.run_id)


def _run_ai_layer(db: Session, run: ScreenRun, config: ScreenConfig, layer: str) -> None:
    """稳健层 / 风险层：仅处理存活集，更新各行。"""
    eval_fn = _LAYER_EVAL[layer]
    company_ids = _alive_company_ids(db, run.run_id)
    _set_run(db, run.run_id, current_layer=layer, layer_status="running",
             progress_count=0, current_company_name=None)

    for idx, cid in enumerate(company_ids, 1):
        sr = db.execute(
            select(ScreenResult).where(
                ScreenResult.run_id == run.run_id, ScreenResult.company_id == cid
            ).limit(1)
        ).scalar()
        if sr is None:
            _set_run(db, run.run_id, progress_count=idx)
            continue
        try:
            alive, layer_res = eval_fn(db, cid, run.as_of_date, config, run.user_id, run.run_id)
            results = dict(sr.layer_results or {})
            results[layer] = layer_res
            sr.layer_results = results
            merged = list(sr.reason_codes or []) + list(layer_res.get("reason_codes") or [])
            sr.reason_codes = merged
            snap = dict(sr.metrics_snapshot or {})
            snap.update(layer_res.get("metrics") or {})
            sr.metrics_snapshot = snap
            if layer_res.get("ai_result_id"):
                sr.ai_result_id = layer_res["ai_result_id"]
            if not alive:
                sr.rejected_at_layer = layer
                sr.status = "Rejected"
            db.add(sr)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.exception("%s layer failed for %s: %s", layer, cid, e)
        comp = db.get(Company, cid)
        _set_run(db, run.run_id, progress_count=idx,
                 current_company_name=comp.name if comp else None)

    _recount(db, run.run_id)


def _run_one_layer(db: Session, run_id: int, layer: str) -> None:
    run = db.get(ScreenRun, run_id)
    config = _config_from_run(run)
    if layer == "roce":
        _run_roce_layer(db, run, config)
    else:
        _run_ai_layer(db, run, config, layer)


def _finalize(db: Session, run_id: int) -> None:
    """三层跑完：存活者状态置 HighConviction，run 终态。"""
    db.execute(
        update(ScreenResult)
        .where(ScreenResult.run_id == run_id, ScreenResult.rejected_at_layer.is_(None))
        .values(status="HighConviction")
    )
    db.commit()
    _recount(db, run_id)
    _set_run(db, run_id, current_layer="done", layer_status="completed",
             status="completed", finished_at=datetime.now(), current_company_name=None)


def run_from(run_id: int, start_layer: str) -> None:
    """从 start_layer 开始执行。auto_advance=True 则连跑到 done；否则跑一层停在 awaiting_review。

    后台任务入口（自带 DB 会话）。
    """
    db = SessionLocal()
    try:
        layer = start_layer
        while layer in LAYERS:
            _run_one_layer(db, run_id, layer)
            run = db.get(ScreenRun, run_id)
            nxt = _NEXT[layer]
            if run.auto_advance:
                if nxt == "done":
                    _finalize(db, run_id)
                    return
                layer = nxt
                continue
            # 非 auto（auto_advance=False）：每层跑完停在 awaiting_review。
            # 注：HTTP 人工 gate 端点（/advance、/manual）已移除，此分支当前无外部推进入口，
            # 仅保留引擎能力；默认全自动见上方 auto_advance 分支。
            _set_run(db, run_id, current_layer=layer, layer_status="awaiting_review",
                     current_company_name=None)
            return
    except Exception as e:  # noqa: BLE001
        log.exception("run_from failed run=%s layer=%s: %s", run_id, start_layer, e)
        _set_run(db, run_id, layer_status="failed", status="failed",
                 error_msg=str(e)[:500])
    finally:
        db.close()


def start_run(run_id: int) -> None:
    """初次启动：从 ROCE 层开始。"""
    run_from(run_id, "roce")


def finalize_run(run_id: int) -> None:
    """风险层复核完成后定稿（存活者置 HighConviction + completed）。后台任务入口。"""
    db = SessionLocal()
    try:
        _finalize(db, run_id)
    except Exception as e:  # noqa: BLE001
        log.exception("finalize_run failed run=%s: %s", run_id, e)
        _set_run(db, run_id, layer_status="failed", status="failed",
                 error_msg=str(e)[:500])
    finally:
        db.close()
