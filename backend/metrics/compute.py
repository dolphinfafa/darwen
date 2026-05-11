# -*- coding: utf-8 -*-
"""指标预计算调度器：将 ROCE 等指标落库到 metric_periodic + 血缘日志。

当前覆盖：
- 年度指标：roce, ebit, capital_employed, nwc_ex_cash, operating_current_assets,
  operating_current_liabilities, net_ppe
- 截面指标（as_of=最新 period_end）：roce_5y_median, roce_10y_median,
  q3_pass_5y, q4_strong_track_record

写库策略：INSERT ON DUPLICATE KEY UPDATE，按
(company_id, period_end, metric_name, formula_version) 去重。

血缘日志：每个分量字段 → 一行 metric_lineage_log，source_code 取自 fact.source_type。
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.fact import Fact
from backend.models.metric_lineage_log import MetricLineageLog
from backend.models.metric_periodic import MetricPeriodic

from backend.metrics.cash_quality import (
    CashQualityComponents,
    FORMULA_VERSION as CASH_QUALITY_FORMULA_VERSION,
    compute_cash_quality_series,
    evaluate_cash_quality_gate,
)
from backend.metrics.dilution import (
    DilutionYear,
    FORMULA_VERSION as DILUTION_FORMULA_VERSION,
    compute_dilution_series,
    evaluate_dilution_gate,
)
from backend.metrics.helpers import _get_market, get_fiscal_year_end
from backend.metrics.leverage import (
    FORMULA_VERSION as LEVERAGE_FORMULA_VERSION,
    LeverageComponents,
    compute_leverage_series,
)
from backend.metrics.roce import (
    FORMULA_VERSION,
    QualityGate,
    RoceComponents,
    compute_roce_series,
    evaluate_quality_gate,
)
from backend.metrics.valuation import (
    FORMULA_VERSION as VALUATION_FORMULA_VERSION,
    compute_valuation_snapshot,
)


log = logging.getLogger(__name__)


_YEAR_METRICS = (
    "roce",
    "ebit",
    "capital_employed",
    "nwc_ex_cash",
    "operating_current_assets",
    "operating_current_liabilities",
    "net_ppe",
)

_SECTION_METRICS = (
    "roce_5y_median",
    "roce_10y_median",
    "q3_pass_5y",
    "q4_strong_track_record",
)


_LEVERAGE_YEAR_METRICS = (
    "net_debt",
    "net_debt_ebit",
    "interest_coverage",
    "current_ratio",
)

_CASH_QUALITY_YEAR_METRICS = (
    "cfo_ni_ratio",
    "fcf",
)

_CASH_QUALITY_SECTION_METRICS = (
    "cfo_ni_5y_below_07_years",
    "cfo_ni_5y_consec_below_07",
    "fcf_neg_5y_years",
    "median_cfo_ni_5y",
)

_DILUTION_YEAR_METRICS = (
    "shares_outstanding",
)

_DILUTION_SECTION_METRICS = (
    "share_count_cagr_5y",
)

_VALUATION_SECTION_METRICS = (
    "market_cap",
    "pe_ttm",
    "ev_ebit",
    "enterprise_value",
)


def _build_fact_meta_lookup(
    db: Session, fact_ids: Iterable[Optional[str]]
) -> dict[str, tuple[str, Optional[float], Optional[date]]]:
    """批量查 fact_id → (source_type, value, accepted_date) 映射。用于血缘日志。"""
    ids = [fid for fid in fact_ids if fid]
    if not ids:
        return {}
    rows = db.execute(
        select(Fact.fact_id, Fact.source_type, Fact.value, Fact.accepted_date).where(
            Fact.fact_id.in_(set(ids))
        )
    ).all()
    return {r.fact_id: (r.source_type, r.value, r.accepted_date) for r in rows}


def _upsert_metric(
    db: Session,
    company_id: str,
    period_end: date,
    metric_name: str,
    value: Optional[float],
    source_fact_ids: list[Optional[str]],
    notes: Optional[str],
    *,
    formula_version: str = FORMULA_VERSION,
) -> None:
    """对 metric_periodic 做 upsert（按唯一键去重）。"""
    cleaned_ids = [fid for fid in source_fact_ids if fid]
    stmt = mysql_insert(MetricPeriodic).values(
        company_id=company_id,
        period_end=period_end,
        metric_name=metric_name,
        formula_version=formula_version,
        value=value,
        source_fact_ids=cleaned_ids if cleaned_ids else None,
        notes=notes,
    )
    stmt = stmt.on_duplicate_key_update(
        value=stmt.inserted.value,
        source_fact_ids=stmt.inserted.source_fact_ids,
        notes=stmt.inserted.notes,
        computed_at=func.now(),
    )
    db.execute(stmt)


def _write_lineage_rows(
    db: Session,
    company_id: str,
    period_end: date,
    fact_id_map: dict[str, Optional[str]],
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    derived_raw_values: dict[str, Optional[float]],
    *,
    formula_version: str = FORMULA_VERSION,
) -> None:
    """为单年的所有输入字段写血缘日志。

    - fact_id_map: 输入字段名 → fact_id（None 表示该字段缺失被置 0）
    - fact_meta_lookup: fact_id → (source_type, raw_value, accepted_date)
    - derived_raw_values: 派生字段（ebit/operating_current_assets/...）→ 计算后值
    """
    rows = []
    for field_name, fact_id in fact_id_map.items():
        if fact_id is None:
            # 缺失被置 0 的字段：仍记录一行供审计追溯
            if field_name in derived_raw_values:
                continue  # 派生字段下面单独处理
            rows.append(
                dict(
                    run_id=None,
                    company_id=company_id,
                    field_name=field_name,
                    source_code="ZERO_FALLBACK",
                    source_record_key=None,
                    period_end=period_end,
                    effective_date=None,
                    raw_value=0.0,
                    normalized_value=None,
                    formula_version=formula_version,
                )
            )
            continue

        meta = fact_meta_lookup.get(fact_id)
        if meta is None:
            continue  # fact_id 在 lookup 缺失（异常），跳过
        source_type, raw_value, accepted_date = meta
        rows.append(
            dict(
                run_id=None,
                company_id=company_id,
                field_name=field_name,
                source_code=source_type,
                source_record_key=fact_id,
                period_end=period_end,
                effective_date=accepted_date,
                raw_value=raw_value,
                normalized_value=derived_raw_values.get(field_name),
                formula_version=formula_version,
            )
        )
    if rows:
        db.execute(mysql_insert(MetricLineageLog), rows)


def _persist_roce(
    db: Session,
    company_id: str,
    roce_series: list[RoceComponents],
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    write_lineage: bool,
) -> tuple[int, int, int, QualityGate]:
    """ROCE 年度 + 截面 + 血缘落库，返回 (year_rows, section_rows, lineage_rows, gate)。"""
    year_rows = 0
    lineage_rows = 0

    for c in roce_series:
        if c.period_end is None:
            continue
        notes_str = ",".join(c.notes) if c.notes else None
        for metric_name in _YEAR_METRICS:
            value = {
                "ebit": c.ebit,
                "capital_employed": c.capital_employed,
                "nwc_ex_cash": c.nwc_ex_cash,
                "operating_current_assets": c.operating_current_assets,
                "operating_current_liabilities": c.operating_current_liabilities,
                "net_ppe": c.net_ppe,
                "roce": c.roce,
            }.get(metric_name)
            _upsert_metric(
                db, company_id, c.period_end, metric_name, value,
                list(c.source_fact_ids.values()), notes_str,
                formula_version=FORMULA_VERSION,
            )
            year_rows += 1

        if write_lineage:
            _write_lineage_rows(
                db, company_id, c.period_end, c.source_fact_ids,
                fact_meta_lookup, {"ebit": c.ebit},
                formula_version=FORMULA_VERSION,
            )
            lineage_rows += len(c.source_fact_ids)

    # 截面 + 5Y/10Y 门槛
    gate = evaluate_quality_gate(roce_series)
    section_rows = 0
    valid_period_ends = [c.period_end for c in roce_series if c.period_end]
    if valid_period_ends:
        as_of = max(valid_period_ends)
        for name, value in {
            "roce_5y_median": gate.median_5y,
            "roce_10y_median": gate.median_10y,
            "q3_pass_5y": 1.0 if gate.pass_5y_gate else 0.0,
            "q4_strong_track_record": 1.0 if gate.strong_track_record else 0.0,
        }.items():
            _upsert_metric(
                db, company_id, as_of, name, value, [],
                gate.fail_reason, formula_version=FORMULA_VERSION,
            )
            section_rows += 1

    return year_rows, section_rows, lineage_rows, gate


def _persist_leverage(
    db: Session,
    company_id: str,
    lev_series: list[LeverageComponents],
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    write_lineage: bool,
) -> tuple[int, int]:
    year_rows = 0
    lineage_rows = 0
    for c in lev_series:
        if c.period_end is None:
            continue
        notes_str = ",".join(c.notes) if c.notes else None
        for metric_name in _LEVERAGE_YEAR_METRICS:
            value = {
                "net_debt": c.net_debt,
                "net_debt_ebit": c.net_debt_ebit,
                "interest_coverage": c.interest_coverage,
                "current_ratio": c.current_ratio,
            }.get(metric_name)
            _upsert_metric(
                db, company_id, c.period_end, metric_name, value,
                list(c.source_fact_ids.values()), notes_str,
                formula_version=LEVERAGE_FORMULA_VERSION,
            )
            year_rows += 1
        if write_lineage:
            _write_lineage_rows(
                db, company_id, c.period_end, c.source_fact_ids,
                fact_meta_lookup, {},
                formula_version=LEVERAGE_FORMULA_VERSION,
            )
            lineage_rows += len(c.source_fact_ids)
    return year_rows, lineage_rows


def _persist_cash_quality(
    db: Session,
    company_id: str,
    cq_series: list[CashQualityComponents],
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    write_lineage: bool,
) -> tuple[int, int, int]:
    year_rows = 0
    lineage_rows = 0
    for c in cq_series:
        if c.period_end is None:
            continue
        notes_str = ",".join(c.notes) if c.notes else None
        for metric_name in _CASH_QUALITY_YEAR_METRICS:
            value = {"cfo_ni_ratio": c.cfo_ni_ratio, "fcf": c.fcf}.get(metric_name)
            _upsert_metric(
                db, company_id, c.period_end, metric_name, value,
                list(c.source_fact_ids.values()), notes_str,
                formula_version=CASH_QUALITY_FORMULA_VERSION,
            )
            year_rows += 1
        if write_lineage:
            _write_lineage_rows(
                db, company_id, c.period_end, c.source_fact_ids,
                fact_meta_lookup, {"fcf": c.fcf},
                formula_version=CASH_QUALITY_FORMULA_VERSION,
            )
            lineage_rows += len(c.source_fact_ids)

    # 截面统计：cfo_ni_5y_below_07_years / consec_below / fcf_neg_5y_years / median_cfo_ni_5y
    gate = evaluate_cash_quality_gate(cq_series)
    section_rows = 0
    valid_period_ends = [c.period_end for c in cq_series if c.period_end]
    if valid_period_ends:
        as_of = max(valid_period_ends)
        for name, value in {
            "cfo_ni_5y_below_07_years": float(gate.cfo_ni_5y_below_07_years),
            "cfo_ni_5y_consec_below_07": float(gate.cfo_ni_5y_consec_below_07),
            "fcf_neg_5y_years": float(gate.fcf_neg_5y_years),
            "median_cfo_ni_5y": gate.median_cfo_ni_5y,
        }.items():
            _upsert_metric(
                db, company_id, as_of, name, value, [], None,
                formula_version=CASH_QUALITY_FORMULA_VERSION,
            )
            section_rows += 1
    return year_rows, section_rows, lineage_rows


def _persist_dilution(
    db: Session,
    company_id: str,
    dil_series: list[DilutionYear],
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    write_lineage: bool,
) -> tuple[int, int, int]:
    """落库年度 shares_outstanding + 截面 share_count_cagr_5y。"""
    year_rows = 0
    lineage_rows = 0
    for c in dil_series:
        if c.period_end is None or c.shares_outstanding is None:
            continue
        _upsert_metric(
            db, company_id, c.period_end, "shares_outstanding",
            c.shares_outstanding,
            [c.source_fact_id] if c.source_fact_id else [],
            None,
            formula_version=DILUTION_FORMULA_VERSION,
        )
        year_rows += 1
        if write_lineage and c.source_fact_id:
            _write_lineage_rows(
                db, company_id, c.period_end,
                {"shares_outstanding": c.source_fact_id},
                fact_meta_lookup, {},
                formula_version=DILUTION_FORMULA_VERSION,
            )
            lineage_rows += 1

    # 截面
    gate = evaluate_dilution_gate(dil_series)
    section_rows = 0
    valid_period_ends = [c.period_end for c in dil_series if c.period_end]
    if valid_period_ends and gate.share_count_cagr_5y is not None:
        as_of = max(valid_period_ends)
        notes = ",".join(gate.notes) if gate.notes else None
        _upsert_metric(
            db, company_id, as_of, "share_count_cagr_5y",
            gate.share_count_cagr_5y, [], notes,
            formula_version=DILUTION_FORMULA_VERSION,
        )
        section_rows += 1
    return year_rows, section_rows, lineage_rows


def _persist_valuation(
    db: Session,
    company_id: str,
    snap,
    fact_meta_lookup: dict[str, tuple[str, Optional[float], Optional[date]]],
    write_lineage: bool,
) -> tuple[int, int]:
    """落库估值截面（market_cap / pe_ttm / ev_ebit / enterprise_value）。

    period_end 取 snap.latest_trade_date（如有），fallback shares_period_end。
    """
    if snap.latest_trade_date is None and snap.shares_period_end is None:
        return 0, 0
    period_end = snap.latest_trade_date or snap.shares_period_end
    notes_str = ",".join(snap.notes) if snap.notes else None
    section_rows = 0
    for metric_name in _VALUATION_SECTION_METRICS:
        value = {
            "market_cap": snap.market_cap,
            "pe_ttm": snap.pe_ttm,
            "ev_ebit": snap.ev_ebit,
            "enterprise_value": snap.enterprise_value,
        }.get(metric_name)
        _upsert_metric(
            db, company_id, period_end, metric_name, value,
            list(snap.source_fact_ids.values()), notes_str,
            formula_version=VALUATION_FORMULA_VERSION,
        )
        section_rows += 1
    lineage_rows = 0
    if write_lineage and snap.source_fact_ids:
        _write_lineage_rows(
            db, company_id, period_end, snap.source_fact_ids,
            fact_meta_lookup, {},
            formula_version=VALUATION_FORMULA_VERSION,
        )
        lineage_rows = len(snap.source_fact_ids)
    return section_rows, lineage_rows


def persist_all_metrics_for_company(
    db: Session,
    company_id: str,
    *,
    year_range: tuple[int, int] = (2014, 2024),
    market: Optional[str] = None,
    write_lineage: bool = True,
    valuation_asof: Optional[date] = None,
) -> dict:
    """对单家公司全量计算并落库 ROCE + Leverage + CashQuality 指标。"""
    if market is None:
        market = _get_market(db, company_id)
    if market is None:
        return {"error": "company_not_found", "company_id": company_id}

    fy_end_month = get_fiscal_year_end(db, company_id, market=market)

    # 1. ROCE（先算，提供 EBIT 给 leverage）
    roce_series: list[RoceComponents] = compute_roce_series(
        db, company_id, year_range, market=market, fiscal_year_end_month=fy_end_month
    )
    ebit_by_year = {c.year: c.ebit for c in roce_series if c.ebit is not None}

    # 2. Leverage（消费 EBIT）
    lev_series: list[LeverageComponents] = compute_leverage_series(
        db, company_id, year_range, market=market,
        fiscal_year_end_month=fy_end_month, ebit_by_year=ebit_by_year,
    )

    # 3. Cash Quality
    cq_series: list[CashQualityComponents] = compute_cash_quality_series(
        db, company_id, year_range, market=market, fiscal_year_end_month=fy_end_month,
    )

    # 4. Dilution（shares_outstanding 历史 + 5Y CAGR）
    dil_series: list[DilutionYear] = compute_dilution_series(
        db, company_id, year_range, market=market, fiscal_year_end_month=fy_end_month,
    )

    # 5. Valuation 截面（默认 as_of = year_range 末年 12-31，反映回测点时；可显式覆盖）
    val_asof = valuation_asof or date(year_range[1], 12, 31)
    val_snap = compute_valuation_snapshot(db, company_id, val_asof, market=market)

    # 6. 统一收集 fact_ids 一次性查源元数据
    all_fact_ids: list[Optional[str]] = []
    for c in roce_series:
        all_fact_ids.extend(c.source_fact_ids.values())
    for c in lev_series:
        all_fact_ids.extend(c.source_fact_ids.values())
    for c in cq_series:
        all_fact_ids.extend(c.source_fact_ids.values())
    for c in dil_series:
        if c.source_fact_id:
            all_fact_ids.append(c.source_fact_id)
    all_fact_ids.extend(val_snap.source_fact_ids.values())
    fact_meta_lookup = _build_fact_meta_lookup(db, all_fact_ids)

    # 7. 落库
    roce_year, roce_section, roce_lineage, gate = _persist_roce(
        db, company_id, roce_series, fact_meta_lookup, write_lineage
    )
    lev_year, lev_lineage = _persist_leverage(
        db, company_id, lev_series, fact_meta_lookup, write_lineage
    )
    cq_year, cq_section, cq_lineage = _persist_cash_quality(
        db, company_id, cq_series, fact_meta_lookup, write_lineage
    )
    dil_year, dil_section, dil_lineage = _persist_dilution(
        db, company_id, dil_series, fact_meta_lookup, write_lineage
    )
    val_section, val_lineage = _persist_valuation(
        db, company_id, val_snap, fact_meta_lookup, write_lineage
    )

    db.commit()

    return {
        "company_id": company_id,
        "year_rows": roce_year + lev_year + cq_year + dil_year,
        "section_rows": roce_section + cq_section + dil_section + val_section,
        "lineage_rows": roce_lineage + lev_lineage + cq_lineage + dil_lineage + val_lineage,
        "valid_5y": gate.n_valid_years,
        "valid_10y": gate.n_valid_10y,
        "median_5y": gate.median_5y,
        "pass_5y": gate.pass_5y_gate,
        "strong": gate.strong_track_record,
        "fail_reason": gate.fail_reason,
        "pe_ttm": val_snap.pe_ttm,
        "share_cagr_5y": evaluate_dilution_gate(dil_series).share_count_cagr_5y,
    }


# 向后兼容别名
persist_roce_for_company = persist_all_metrics_for_company


def persist_all_metrics_bulk(
    company_ids: Optional[list[str]] = None,
    *,
    year_range: tuple[int, int] = (2014, 2024),
    log_every: int = 25,
) -> dict:
    """批量回填多家公司。company_ids 为 None 时跑全部 company。"""
    db = SessionLocal()
    try:
        if company_ids is None:
            company_ids = [
                row[0] for row in db.execute(select(Company.company_id)).all()
            ]

        total = len(company_ids)
        ok = 0
        errors: list[tuple[str, str]] = []
        agg_year = 0
        agg_section = 0
        agg_lineage = 0
        pass_5y_count = 0
        strong_count = 0

        for i, cid in enumerate(company_ids, 1):
            try:
                stats = persist_all_metrics_for_company(db, cid, year_range=year_range)
                if "error" in stats:
                    errors.append((cid, stats["error"]))
                    continue
                ok += 1
                agg_year += stats["year_rows"]
                agg_section += stats["section_rows"]
                agg_lineage += stats["lineage_rows"]
                if stats["pass_5y"]:
                    pass_5y_count += 1
                if stats["strong"]:
                    strong_count += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append((cid, str(e)[:200]))
                log.exception("persist_all_metrics_for_company failed for %s", cid)

            if i % log_every == 0:
                log.info("进度 %d/%d (ok=%d, errors=%d)", i, total, ok, len(errors))

        return {
            "total": total,
            "ok": ok,
            "errors": errors,
            "year_rows": agg_year,
            "section_rows": agg_section,
            "lineage_rows": agg_lineage,
            "pass_5y_count": pass_5y_count,
            "strong_count": strong_count,
        }
    finally:
        db.close()


# 向后兼容别名
persist_roce_bulk = persist_all_metrics_bulk


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Darwen V2 ROCE 全量回填")
    parser.add_argument("--company", action="append", help="指定 company_id（可多次）；不传则全部")
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    result = persist_all_metrics_bulk(
        company_ids=args.company,
        year_range=(args.start_year, args.end_year),
    )
    # errors 太长不打印
    summary = {k: v for k, v in result.items() if k != "errors"}
    summary["error_count"] = len(result["errors"])
    print(json.dumps(summary, indent=2, default=str))
    if result["errors"]:
        print("\n前 5 个错误：")
        for cid, msg in result["errors"][:5]:
            print(f"  {cid}: {msg}")
