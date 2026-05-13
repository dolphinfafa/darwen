# -*- coding: utf-8 -*-
"""一次性填充 company.fiscal_year_end_month。

- 美股：调 SEC submissions 取 fiscalYearEnd 字段（MMDD 格式，取月份）
- A 股：一律 12（pro forma 财年）

启发式 get_fiscal_year_end 对 TSLA / NVDA 等公司失败：
  - TSLA 推断 3 月（实际 12 月）
  - NVDA 推断 10 月（实际 1 月）
权威字段从 SEC submissions 来。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.pipeline.sec_edgar.submissions import fetch_submission


log = logging.getLogger(__name__)


def _parse_mmdd_month(mmdd: str) -> Optional[int]:
    if not mmdd or len(mmdd) != 4:
        return None
    try:
        m = int(mmdd[:2])
        return m if 1 <= m <= 12 else None
    except ValueError:
        return None


def fill_us(db: Session, *, log_every: int = 50) -> dict:
    rows = db.execute(
        select(Company.company_id, Company.cik).where(Company.market == "US")
    ).all()
    total = len(rows)
    ok = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    for i, (cid, cik) in enumerate(rows, 1):
        if not cik:
            skipped += 1
            continue
        try:
            data = fetch_submission(cik.lstrip("0") or "0")
            if not data:
                skipped += 1
                continue
            month = _parse_mmdd_month(data.get("fiscalYearEnd", ""))
            if month is None:
                skipped += 1
                continue
            db.execute(
                update(Company)
                .where(Company.company_id == cid)
                .values(fiscal_year_end_month=month)
            )
            ok += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            errors.append((cid, str(e)[:200]))
            log.exception("fill fye failed for %s", cid)
        if i % log_every == 0:
            log.info("进度 %d/%d ok=%d skipped=%d errors=%d", i, total, ok, skipped, len(errors))

    db.commit()
    return {"total": total, "ok": ok, "skipped": skipped, "errors": errors}


def fill_cn(db: Session) -> int:
    """A 股一律 12 月。"""
    result = db.execute(
        update(Company).where(Company.market == "CN_A").values(fiscal_year_end_month=12)
    )
    db.commit()
    return result.rowcount


def fill_all() -> dict:
    db = SessionLocal()
    try:
        cn_n = fill_cn(db)
        log.info("A 股填充 %d 家 (=12)", cn_n)
        us_stats = fill_us(db)
        us_stats["cn_filled"] = cn_n
        return us_stats
    finally:
        db.close()


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = fill_all()
    summary = {k: v for k, v in res.items() if k != "errors"}
    summary["error_count"] = len(res.get("errors", []))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
