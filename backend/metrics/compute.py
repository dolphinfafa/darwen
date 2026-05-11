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

from backend.metrics.helpers import _get_market, get_fiscal_year_end
from backend.metrics.roce import (
    FORMULA_VERSION,
    QualityGate,
    RoceComponents,
    compute_roce_series,
    evaluate_quality_gate,
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
) -> None:
    """对 metric_periodic 做 upsert（按唯一键去重）。"""
    cleaned_ids = [fid for fid in source_fact_ids if fid]
    stmt = mysql_insert(MetricPeriodic).values(
        company_id=company_id,
        period_end=period_end,
        metric_name=metric_name,
        formula_version=FORMULA_VERSION,
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
                    formula_version=FORMULA_VERSION,
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
                formula_version=FORMULA_VERSION,
            )
        )
    if rows:
        db.execute(mysql_insert(MetricLineageLog), rows)


def persist_roce_for_company(
    db: Session,
    company_id: str,
    *,
    year_range: tuple[int, int] = (2014, 2024),
    market: Optional[str] = None,
    write_lineage: bool = True,
) -> dict:
    """对单家公司全量计算并落库 ROCE 相关指标。

    返回 stats dict：{year_rows, section_rows, lineage_rows, valid_years, pass_5y, strong}
    """
    if market is None:
        market = _get_market(db, company_id)
    if market is None:
        return {"error": "company_not_found", "company_id": company_id}

    fy_end_month = get_fiscal_year_end(db, company_id, market=market)
    series: list[RoceComponents] = compute_roce_series(
        db, company_id, year_range, market=market, fiscal_year_end_month=fy_end_month
    )

    # 批量查 fact_id → (source_type, raw_value, accepted_date)
    all_fact_ids: list[Optional[str]] = []
    for c in series:
        all_fact_ids.extend(c.source_fact_ids.values())
    fact_meta_lookup = _build_fact_meta_lookup(db, all_fact_ids)

    year_rows = 0
    lineage_rows = 0

    for c in series:
        if c.period_end is None:
            continue  # 完全无数据，跳过
        # 即使 ROCE 为 None（NEGATIVE_CAP_EMP / 缺数据），也落库 ebit/capital_employed 等中间值
        # 以便 R 层/审计可见。roce 字段会为 NULL。
        notes_str = ",".join(c.notes) if c.notes else None
        # 该年所有分量的原始值快照（写血缘用）
        raw_values = {
            "ebit": c.ebit,
            "operating_current_assets": c.operating_current_assets,
            "operating_current_liabilities": c.operating_current_liabilities,
            "nwc_ex_cash": c.nwc_ex_cash,
            "net_ppe": c.net_ppe,
            "capital_employed": c.capital_employed,
            "roce": c.roce,
        }
        for metric_name in _YEAR_METRICS:
            value = raw_values.get(metric_name) if metric_name != "roce" else c.roce
            if metric_name == "ebit":
                value = c.ebit
            elif metric_name == "capital_employed":
                value = c.capital_employed
            elif metric_name == "nwc_ex_cash":
                value = c.nwc_ex_cash
            elif metric_name == "operating_current_assets":
                value = c.operating_current_assets
            elif metric_name == "operating_current_liabilities":
                value = c.operating_current_liabilities
            elif metric_name == "net_ppe":
                value = c.net_ppe
            elif metric_name == "roce":
                value = c.roce
            _upsert_metric(
                db,
                company_id,
                c.period_end,
                metric_name,
                value,
                list(c.source_fact_ids.values()),
                notes_str,
            )
            year_rows += 1

        if write_lineage:
            # normalized_value 仅对派生字段（ebit）有意义；输入字段的 normalized 留空
            derived = {"ebit": c.ebit}
            _write_lineage_rows(
                db,
                company_id,
                c.period_end,
                c.source_fact_ids,
                fact_meta_lookup,
                derived,
            )
            lineage_rows += len(c.source_fact_ids)

    # 截面指标：取 series 中最大的 period_end 作为 as_of
    gate: QualityGate = evaluate_quality_gate(series)
    valid_period_ends = [c.period_end for c in series if c.period_end]
    section_rows = 0
    if valid_period_ends:
        as_of = max(valid_period_ends)
        section_values = {
            "roce_5y_median": gate.median_5y,
            "roce_10y_median": gate.median_10y,
            "q3_pass_5y": 1.0 if gate.pass_5y_gate else 0.0,
            "q4_strong_track_record": 1.0 if gate.strong_track_record else 0.0,
        }
        notes = gate.fail_reason if gate.fail_reason else None
        for name, value in section_values.items():
            _upsert_metric(db, company_id, as_of, name, value, [], notes)
            section_rows += 1

    db.commit()

    return {
        "company_id": company_id,
        "year_rows": year_rows,
        "section_rows": section_rows,
        "lineage_rows": lineage_rows,
        "valid_5y": gate.n_valid_years,
        "valid_10y": gate.n_valid_10y,
        "median_5y": gate.median_5y,
        "pass_5y": gate.pass_5y_gate,
        "strong": gate.strong_track_record,
        "fail_reason": gate.fail_reason,
    }


def persist_roce_bulk(
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
                stats = persist_roce_for_company(db, cid, year_range=year_range)
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
                log.exception("persist_roce_for_company failed for %s", cid)

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


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Darwen V2 ROCE 全量回填")
    parser.add_argument("--company", action="append", help="指定 company_id（可多次）；不传则全部")
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    result = persist_roce_bulk(
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
