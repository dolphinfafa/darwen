# -*- coding: utf-8 -*-
"""
Darwen V1.0 Scoring Engine — 4-Layer Funnel Model

Layer A: Hard Reject Filters (F1-F4)
Layer B: Quality Engine (Q1-Q3, 0-100)
Layer C: Fair Price Gate (PE-based)
Layer D: Final Status (BUY / WATCH / TOO_EXPENSIVE / REJECT)
"""
import hashlib
import json
import statistics
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.factors.helpers import (
    get_annual_values,
    get_fact_value,
    get_revenue_series,
    safe_div,
    cagr,
    get_close_prices,
)
from backend.models import ScoreSnapshot, Company


# ═══════════════════════════════════════════════════════════
#  Concept mapping per market
# ═══════════════════════════════════════════════════════════

_CONCEPTS = {
    "US": {
        "ebit": ["OperatingIncomeLoss"],
        "total_assets": ["Assets"],
        "current_liabilities": ["LiabilitiesCurrent"],
        "net_income": ["NetIncomeLoss"],
        "ocf": ["NetCashProvidedByOperatingActivities"],
        "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "interest_expense": ["InterestExpense"],
        "total_debt": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
        "cash": ["CashAndCashEquivalentsAtCarryingValue"],
        "current_assets": ["AssetsCurrent"],
        "gross_profit": ["GrossProfit"],
        "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
        "shares_outstanding": ["CommonStockSharesOutstanding", "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"],
        "goodwill": ["Goodwill"],
        "dividends_paid": ["PaymentsOfDividends"],
        "buyback": ["PaymentsForRepurchaseOfCommonStock"],
        "operating_income": ["OperatingIncomeLoss"],
        "total_cost": [],  # not used for US
        "operating_profit": ["OperatingIncomeLoss"],
        "eps": ["EarningsPerShareBasic"],
    },
    "CN_A": {
        "ebit": ["operating_income"],
        "total_assets": ["total_assets"],
        "current_liabilities": ["current_liabilities"],
        "net_income": ["net_income", "net_profit"],
        "ocf": ["operating_cash_flow", "net_cash_from_operating"],
        "capex": ["capital_expenditure", "capex"],
        "interest_expense": ["interest_expense"],
        "total_debt": ["total_debt", "long_term_debt"],
        "cash": ["cash_and_equivalents", "cash"],
        "current_assets": ["current_assets"],
        "gross_profit": ["gross_profit"],
        "revenue": ["revenue"],
        "shares_outstanding": ["total_shares", "shares_outstanding"],
        "goodwill": ["goodwill"],
        "dividends_paid": ["dividends_paid"],
        "buyback": ["share_buyback"],
        "operating_income": ["operating_income"],
        "total_cost": ["total_cost", "operating_cost"],
        "operating_profit": ["operating_income"],
        "eps": ["eps_basic", "eps"],
    },
}


def _resolve_market(db: Session, company_id: str, market: str | None) -> str:
    """Determine market from company record if not provided."""
    if market:
        return market
    row = db.query(Company.market).filter(Company.company_id == company_id).first()
    return row[0] if row else "US"


def _get_val(db: Session, company_id: str, key: str, asof: date, market: str, lookback: int = 400) -> Optional[float]:
    """Try each concept alias until one returns a value."""
    concepts = _CONCEPTS.get(market, _CONCEPTS["US"]).get(key, [])
    for c in concepts:
        v = get_fact_value(db, company_id, c, asof, lookback)
        if v is not None:
            return v
    return None


def _get_annual(db: Session, company_id: str, key: str, years: int, asof: date, market: str) -> list[float]:
    """Get annual values trying each concept alias."""
    concepts = _CONCEPTS.get(market, _CONCEPTS["US"]).get(key, [])
    for c in concepts:
        vals = get_annual_values(db, company_id, c, years, asof)
        if vals:
            return vals
    return []


# ═══════════════════════════════════════════════════════════
#  Layer A: Hard Reject Filters
# ═══════════════════════════════════════════════════════════

def _filter_f1_roce(db: Session, cid: str, asof: date, mkt: str) -> tuple[bool, str | None]:
    """F1: avg ROCE over 5Y must be >= 20%."""
    ebit_vals = _get_annual(db, cid, "ebit", 5, asof, mkt)
    ta_vals = _get_annual(db, cid, "total_assets", 5, asof, mkt)
    cl_vals = _get_annual(db, cid, "current_liabilities", 5, asof, mkt)

    n = min(len(ebit_vals), len(ta_vals), len(cl_vals))
    if n == 0:
        return False, "Insufficient ROCE data (no annual values found)"

    roces = []
    for i in range(n):
        ce = ta_vals[i] - cl_vals[i]
        r = safe_div(ebit_vals[i], ce)
        if r is not None:
            roces.append(r)

    if not roces:
        return False, "Cannot compute ROCE (capital employed is zero or missing)"

    avg_roce = statistics.mean(roces)
    if avg_roce < 0.20:
        return False, f"Avg ROCE {avg_roce:.1%} < 20% threshold"
    return True, None


def _filter_f2_fragility(db: Session, cid: str, asof: date, mkt: str) -> tuple[bool, str | None]:
    """F2: Financial Fragility checks."""
    # Interest coverage < 3 any of last 3 years
    ebit_3 = _get_annual(db, cid, "ebit", 3, asof, mkt)
    ie_3 = _get_annual(db, cid, "interest_expense", 3, asof, mkt)
    n = min(len(ebit_3), len(ie_3))
    for i in range(n):
        cov = safe_div(ebit_3[i], abs(ie_3[i]) if ie_3[i] else None)
        if cov is not None and cov < 3:
            return False, f"Interest coverage {cov:.2f} < 3 in year {i+1}"

    # Net debt / operating profit > 4
    debt = _get_val(db, cid, "total_debt", asof, mkt)
    cash_val = _get_val(db, cid, "cash", asof, mkt)
    op = _get_val(db, cid, "operating_profit", asof, mkt)
    if debt is not None and cash_val is not None and op is not None and op > 0:
        net_debt = debt - cash_val
        ratio = net_debt / op
        if ratio > 4:
            return False, f"Net debt / operating profit {ratio:.2f} > 4"

    # Current ratio < 1 for 2 consecutive years
    ca_vals = _get_annual(db, cid, "current_assets", 3, asof, mkt)
    cl_vals = _get_annual(db, cid, "current_liabilities", 3, asof, mkt)
    n = min(len(ca_vals), len(cl_vals))
    if n >= 2:
        cr_list = [safe_div(ca_vals[i], cl_vals[i]) for i in range(n)]
        for i in range(n - 1):
            if cr_list[i] is not None and cr_list[i + 1] is not None:
                if cr_list[i] < 1 and cr_list[i + 1] < 1:
                    return False, f"Current ratio < 1 for 2 consecutive years ({cr_list[i]:.2f}, {cr_list[i+1]:.2f})"

    return True, None


def _filter_f3_earnings_quality(db: Session, cid: str, asof: date, mkt: str) -> tuple[bool, str | None]:
    """F3: Earnings Quality checks."""
    ocf_vals = _get_annual(db, cid, "ocf", 5, asof, mkt)
    ni_vals = _get_annual(db, cid, "net_income", 5, asof, mkt)

    # OCF/NI < 0.7 for 2 consecutive years
    n = min(len(ocf_vals), len(ni_vals))
    if n >= 2:
        ratios = [safe_div(ocf_vals[i], ni_vals[i]) for i in range(n)]
        for i in range(n - 1):
            if ratios[i] is not None and ratios[i + 1] is not None:
                if ratios[i] < 0.7 and ratios[i + 1] < 0.7:
                    return False, f"OCF/NI < 0.7 for 2 consecutive years ({ratios[i]:.2f}, {ratios[i+1]:.2f})"

    # FCF checks
    capex_vals = _get_annual(db, cid, "capex", 5, asof, mkt)
    n_fcf = min(len(ocf_vals), len(capex_vals))
    if n_fcf > 0:
        fcf_list = []
        for i in range(n_fcf):
            # capex is typically reported as positive (payments), so FCF = OCF - capex
            fcf = ocf_vals[i] - abs(capex_vals[i])
            fcf_list.append(fcf)

        cum_fcf = sum(fcf_list)
        if cum_fcf <= 0:
            return False, f"5Y cumulative FCF = {cum_fcf:,.0f} <= 0"

        neg_count = sum(1 for f in fcf_list if f < 0)
        if neg_count >= 4:
            return False, f"FCF negative in {neg_count}/5 years"

    return True, None


def _filter_f4_governance(db: Session, cid: str, asof: date, mkt: str) -> tuple[bool, str | None]:
    """F4: Governance / Dilution checks."""
    shares = _get_annual(db, cid, "shares_outstanding", 6, asof, mkt)
    if len(shares) >= 2:
        share_cagr = cagr(shares)
        if share_cagr is not None and share_cagr > 0.03:
            return False, f"Share count CAGR {share_cagr:.1%} > 3%"

    gw = _get_val(db, cid, "goodwill", asof, mkt)
    ta = _get_val(db, cid, "total_assets", asof, mkt)
    if gw is not None and ta is not None and ta > 0:
        ratio = gw / ta
        if ratio > 0.40:
            return False, f"Goodwill/Assets {ratio:.1%} > 40%"

    return True, None


def _run_hard_reject(db: Session, cid: str, asof: date, mkt: str) -> dict:
    """Run all Layer A filters, return structured result."""
    filters = [
        ("F1_ROCE", _filter_f1_roce),
        ("F2_Financial_Fragility", _filter_f2_fragility),
        ("F3_Earnings_Quality", _filter_f3_earnings_quality),
        ("F4_Governance_Dilution", _filter_f4_governance),
    ]
    results = []
    all_passed = True
    for name, fn in filters:
        passed, reason = fn(db, cid, asof, mkt)
        results.append({"name": name, "passed": passed, "reason": reason})
        if not passed:
            all_passed = False

    return {"passed": all_passed, "filters": results}


# ═══════════════════════════════════════════════════════════
#  Layer B: Quality Engine (0-100)
# ═══════════════════════════════════════════════════════════

def _q1_capital_return(db: Session, cid: str, asof: date, mkt: str) -> float:
    """Q1: Capital Return Quality — up to 40 points."""
    score = 0.0

    # --- Q1.1 Avg ROCE level (20 pts) ---
    ebit_vals = _get_annual(db, cid, "ebit", 5, asof, mkt)
    ta_vals = _get_annual(db, cid, "total_assets", 5, asof, mkt)
    cl_vals = _get_annual(db, cid, "current_liabilities", 5, asof, mkt)
    n = min(len(ebit_vals), len(ta_vals), len(cl_vals))
    roces = []
    for i in range(n):
        ce = ta_vals[i] - cl_vals[i]
        r = safe_div(ebit_vals[i], ce)
        if r is not None:
            roces.append(r)

    avg_roce = statistics.mean(roces) if roces else 0
    if avg_roce >= 0.35:
        score += 20
    elif avg_roce >= 0.30:
        score += 16
    elif avg_roce >= 0.25:
        score += 12
    elif avg_roce >= 0.20:
        score += 8

    # --- Q1.2 ROCE stability (10 pts) ---
    if len(roces) >= 2:
        std_roce = statistics.stdev(roces)
        if std_roce < 0.05:
            score += 10
        elif std_roce < 0.08:
            score += 7
        elif std_roce < 0.12:
            score += 4

    # --- Q1.3 Cash conversion (10 pts) ---
    ocf_vals = _get_annual(db, cid, "ocf", 5, asof, mkt)
    n_cc = min(len(ocf_vals), len(ebit_vals))
    if n_cc > 0:
        sum_ocf = sum(ocf_vals[:n_cc])
        sum_ebit = sum(ebit_vals[:n_cc])
        cc = safe_div(sum_ocf, sum_ebit)
        if cc is not None:
            if cc >= 0.9:
                score += 10
            elif cc >= 0.75:
                score += 7
            elif cc >= 0.6:
                score += 4

    return score


def _q2_moat_stability(db: Session, cid: str, asof: date, mkt: str) -> float:
    """Q2: Moat & Stability — up to 35 points."""
    score = 0.0

    # --- Q2.1 Gross margin stability (10 pts) ---
    gp_vals = _get_annual(db, cid, "gross_profit", 5, asof, mkt)
    rev_vals = get_revenue_series(db, cid, 5, asof)
    n_gm = min(len(gp_vals), len(rev_vals))
    if n_gm >= 2:
        gm_list = []
        for i in range(n_gm):
            gm = safe_div(gp_vals[i], rev_vals[i])
            if gm is not None:
                gm_list.append(gm)
        if len(gm_list) >= 2:
            std_gm = statistics.stdev(gm_list)
            if std_gm < 0.03:
                score += 10
            elif std_gm < 0.05:
                score += 7
            elif std_gm < 0.08:
                score += 4

    # --- Q2.2 Revenue continuity (10 pts) ---
    # Need 6 years to compute 5 YoY growth rates
    rev_6 = get_revenue_series(db, cid, 6, asof)
    if len(rev_6) >= 2:
        positive_growth = 0
        growth_periods = len(rev_6) - 1
        for i in range(growth_periods):
            # rev_6 is newest-first, so rev_6[i] > rev_6[i+1] means positive growth
            if rev_6[i] > rev_6[i + 1]:
                positive_growth += 1
        if positive_growth >= 5:
            score += 10
        elif positive_growth >= 4:
            score += 7
        elif positive_growth >= 3:
            score += 4

    # --- Q2.3 Operating margin stability (10 pts) ---
    ebit_vals = _get_annual(db, cid, "ebit", 5, asof, mkt)
    n_om = min(len(ebit_vals), len(rev_vals))
    if n_om >= 2:
        om_list = []
        for i in range(n_om):
            om = safe_div(ebit_vals[i], rev_vals[i])
            if om is not None:
                om_list.append(om)
        if len(om_list) >= 2:
            std_om = statistics.stdev(om_list)
            if std_om < 0.03:
                score += 10
            elif std_om < 0.05:
                score += 7
            elif std_om < 0.08:
                score += 4

    # --- Q2.4 Anti-fragility (5 pts) ---
    if n_om >= 2 and rev_vals:
        margins = []
        for i in range(n_om):
            m = safe_div(ebit_vals[i], rev_vals[i])
            if m is not None:
                margins.append(m)
        if margins:
            min_m = min(margins)
            avg_m = statistics.mean(margins)
            ratio = safe_div(min_m, avg_m)
            if ratio is not None:
                if ratio > 0.7:
                    score += 5
                elif ratio > 0.5:
                    score += 3

    return score


def _q3_capital_allocation(db: Session, cid: str, asof: date, mkt: str) -> float:
    """Q3: Capital Allocation — up to 25 points."""
    score = 0.0

    # --- Q3.1 Incremental ROCE (10 pts) ---
    ebit_vals = _get_annual(db, cid, "ebit", 5, asof, mkt)
    ta_vals = _get_annual(db, cid, "total_assets", 5, asof, mkt)
    cl_vals = _get_annual(db, cid, "current_liabilities", 5, asof, mkt)
    if len(ebit_vals) >= 2 and len(ta_vals) >= 2 and len(cl_vals) >= 2:
        # newest vs oldest
        ce_new = ta_vals[0] - cl_vals[0]
        ce_old = ta_vals[-1] - cl_vals[-1]
        delta_ebit = ebit_vals[0] - ebit_vals[-1]
        delta_ce = ce_new - ce_old
        inc_roce = safe_div(delta_ebit, delta_ce)
        if inc_roce is not None:
            if inc_roce >= 0.25:
                score += 10
            elif inc_roce >= 0.15:
                score += 7
            elif inc_roce >= 0.08:
                score += 4

    # --- Q3.2 Dilution control (5 pts) ---
    shares = _get_annual(db, cid, "shares_outstanding", 6, asof, mkt)
    if len(shares) >= 2:
        share_cagr = cagr(shares)
        if share_cagr is not None:
            if share_cagr <= 0:
                score += 5
            elif share_cagr <= 0.01:
                score += 4
            elif share_cagr <= 0.03:
                score += 2

    # --- Q3.3 Shareholder return (5 pts) ---
    ocf_vals = _get_annual(db, cid, "ocf", 5, asof, mkt)
    capex_vals = _get_annual(db, cid, "capex", 5, asof, mkt)
    div_vals = _get_annual(db, cid, "dividends_paid", 5, asof, mkt)
    bb_vals = _get_annual(db, cid, "buyback", 5, asof, mkt)

    n_sr = min(len(ocf_vals), len(capex_vals))
    if n_sr > 0:
        total_fcf = sum(ocf_vals[i] - abs(capex_vals[i]) for i in range(n_sr))
        total_return = sum(abs(v) for v in div_vals[:n_sr]) + sum(abs(v) for v in bb_vals[:n_sr])
        payout = safe_div(total_return, total_fcf)
        if payout is not None and 0.2 <= payout <= 0.8:
            score += 5
        else:
            score += 2

    # --- Q3.4 M&A discipline (5 pts) ---
    gw = _get_val(db, cid, "goodwill", asof, mkt)
    ta = _get_val(db, cid, "total_assets", asof, mkt)
    if gw is not None and ta is not None and ta > 0:
        ratio = gw / ta
        if ratio < 0.10:
            score += 5
        elif ratio < 0.20:
            score += 3
        elif ratio < 0.30:
            score += 1
    elif gw is None and ta is not None:
        # No goodwill on books = good
        score += 5

    return score


# ═══════════════════════════════════════════════════════════
#  Layer C: Fair Price Gate
# ═══════════════════════════════════════════════════════════

def _get_trailing_pe(db: Session, cid: str, asof: date, mkt: str) -> Optional[float]:
    """Compute trailing PE = price / EPS (TTM)."""
    prices = get_close_prices(db, cid, asof, 5)
    if not prices:
        return None
    latest_price = prices[-1][1]

    eps = _get_val(db, cid, "eps", asof, mkt)
    if eps is not None and eps > 0:
        return latest_price / eps

    # Fallback: NI / shares
    ni = _get_val(db, cid, "net_income", asof, mkt)
    shares = _get_val(db, cid, "shares_outstanding", asof, mkt)
    if ni is not None and shares is not None and ni > 0 and shares > 0:
        computed_eps = ni / shares
        return latest_price / computed_eps

    return None


_TIER_GATES = {
    # (min_quality, min_avg_roce): (pe_buy, pe_watch)
    "A": {"min_q": 85, "min_roce": 0.30, "pe_buy": 22, "pe_watch": 28},
    "B": {"min_q": 70, "min_roce": 0.25, "pe_buy": 18, "pe_watch": 22},
    "C": {"min_q": 55, "min_roce": 0.20, "pe_buy": 15, "pe_watch": 18},
}


def _classify_quality_tier(quality_score: float, avg_roce: float) -> str:
    """Determine quality tier A/B/C/D."""
    for tier_name, g in _TIER_GATES.items():
        if quality_score >= g["min_q"] and avg_roce >= g["min_roce"]:
            return tier_name
    return "D"


def _fair_price_gate(quality_tier: str, trailing_pe: Optional[float]) -> tuple[str, Optional[float]]:
    """Return (gate_result, pe_threshold). gate_result in BUY/WATCH/TOO_EXPENSIVE/None."""
    if quality_tier == "D" or trailing_pe is None:
        return "TOO_EXPENSIVE", None

    g = _TIER_GATES.get(quality_tier)
    if g is None:
        return "TOO_EXPENSIVE", None

    if trailing_pe <= g["pe_buy"]:
        return "BUY", float(g["pe_buy"])
    elif trailing_pe <= g["pe_watch"]:
        return "WATCH", float(g["pe_watch"])
    else:
        return "TOO_EXPENSIVE", float(g["pe_watch"])


# ═══════════════════════════════════════════════════════════
#  Helper: compute avg ROCE for tier classification
# ═══════════════════════════════════════════════════════════

def _compute_avg_roce(db: Session, cid: str, asof: date, mkt: str) -> float:
    """Compute average 5Y ROCE for tier gating."""
    ebit_vals = _get_annual(db, cid, "ebit", 5, asof, mkt)
    ta_vals = _get_annual(db, cid, "total_assets", 5, asof, mkt)
    cl_vals = _get_annual(db, cid, "current_liabilities", 5, asof, mkt)
    n = min(len(ebit_vals), len(ta_vals), len(cl_vals))
    roces = []
    for i in range(n):
        ce = ta_vals[i] - cl_vals[i]
        r = safe_div(ebit_vals[i], ce)
        if r is not None:
            roces.append(r)
    return statistics.mean(roces) if roces else 0.0


# ═══════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════

def score_company_v1(
    db: Session,
    company_id: str,
    asof: date,
    market: str | None = None,
) -> dict:
    """
    V1.0 Scoring Engine — 4-layer funnel model.

    Returns {
        "model_version": "v1.0",
        "hard_reject": {"passed": bool, "filters": [{"name": str, "passed": bool, "reason": str | None}]},
        "quality_score": float | None,  # 0-100, None if rejected
        "quality_tier": str | None,  # A/B/C/D
        "quality_details": {"Q1": float, "Q2": float, "Q3": float},
        "fair_price": {"trailing_pe": float | None, "gate_result": str | None, "pe_threshold": float | None},
        "status": str,  # BUY / WATCH / TOO_EXPENSIVE / REJECT
        "reject_reasons": [str],
    }
    """
    mkt = _resolve_market(db, company_id, market)

    # ── Layer A: Hard Reject ──
    hard_reject = _run_hard_reject(db, company_id, asof, mkt)
    reject_reasons = [f["reason"] for f in hard_reject["filters"] if not f["passed"] and f["reason"]]

    if not hard_reject["passed"]:
        result = {
            "model_version": "v1.0",
            "hard_reject": hard_reject,
            "quality_score": None,
            "quality_tier": None,
            "quality_details": {"Q1": 0.0, "Q2": 0.0, "Q3": 0.0},
            "fair_price": {"trailing_pe": None, "gate_result": None, "pe_threshold": None},
            "status": "REJECT",
            "reject_reasons": reject_reasons,
        }
        _persist_snapshot(db, company_id, asof, result)
        logger.info(f"V1.0 REJECT {company_id}: {reject_reasons}")
        return result

    # ── Layer B: Quality Engine ──
    q1 = _q1_capital_return(db, company_id, asof, mkt)
    q2 = _q2_moat_stability(db, company_id, asof, mkt)
    q3 = _q3_capital_allocation(db, company_id, asof, mkt)
    quality_score = q1 + q2 + q3

    avg_roce = _compute_avg_roce(db, company_id, asof, mkt)
    quality_tier = _classify_quality_tier(quality_score, avg_roce)

    # ── Layer C: Fair Price Gate ──
    trailing_pe = _get_trailing_pe(db, company_id, asof, mkt)
    gate_result, pe_threshold = _fair_price_gate(quality_tier, trailing_pe)

    status = gate_result  # BUY / WATCH / TOO_EXPENSIVE

    result = {
        "model_version": "v1.0",
        "hard_reject": hard_reject,
        "quality_score": round(quality_score, 2),
        "quality_tier": quality_tier,
        "quality_details": {"Q1": round(q1, 2), "Q2": round(q2, 2), "Q3": round(q3, 2)},
        "fair_price": {
            "trailing_pe": round(trailing_pe, 2) if trailing_pe is not None else None,
            "gate_result": gate_result,
            "pe_threshold": pe_threshold,
        },
        "status": status,
        "reject_reasons": reject_reasons,
    }

    _persist_snapshot(db, company_id, asof, result)
    logger.info(
        f"V1.0 {company_id}: score={quality_score:.1f}, tier={quality_tier}, "
        f"PE={trailing_pe}, status={status}"
    )
    return result


# ═══════════════════════════════════════════════════════════
#  Persistence — store into ScoreSnapshot
# ═══════════════════════════════════════════════════════════

def _persist_snapshot(db: Session, company_id: str, asof: date, result: dict):
    """Save result to ScoreSnapshot with model_version='v1.0'."""
    score_id = hashlib.md5(f"{company_id}_{asof}_v1.0".encode()).hexdigest()

    existing = db.get(ScoreSnapshot, score_id)
    if existing:
        snapshot = existing
    else:
        snapshot = ScoreSnapshot(score_id=score_id)
        db.add(snapshot)

    snapshot.company_id = company_id
    snapshot.asof_date = asof
    snapshot.model_version = "v1.0"
    snapshot.total = result.get("quality_score")

    # Normalize sub-scores to 0-100 scale for storage
    q1 = result["quality_details"]["Q1"]
    q2 = result["quality_details"]["Q2"]
    q3 = result["quality_details"]["Q3"]

    # Q1 max=40, Q2 max=35, Q3 max=25 → normalize to 0-100
    snapshot.survival = round((q1 / 40.0) * 100, 2) if q1 is not None else None
    snapshot.moat = round((q2 / 35.0) * 100, 2) if q2 is not None else None
    snapshot.replication = round((q3 / 25.0) * 100, 2) if q3 is not None else None

    # Unused dimensions in v1.0
    snapshot.adaptation = None
    snapshot.valuation = None

    snapshot.tier = result["status"]  # BUY / WATCH / TOO_EXPENSIVE / REJECT
    snapshot.gating_flags = json.dumps(result["reject_reasons"]) if result["reject_reasons"] else None

    db.commit()
