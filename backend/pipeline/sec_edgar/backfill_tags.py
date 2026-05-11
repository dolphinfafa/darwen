# -*- coding: utf-8 -*-
"""SEC 增量回填脚本：对 DB 中已存在的美股全部重新跑 companyfacts，
拉新加入 CORE_CONCEPTS 的 tag。已有 fact_id 不会重复（按哈希去重）。
"""
import logging
import time

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models.company import Company
from backend.pipeline.sec_edgar.company_facts import (
    fetch_company_facts,
    parse_and_store_facts,
)


log = logging.getLogger(__name__)


def backfill_all_us(*, log_every: int = 20) -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Company.company_id, Company.cik).where(Company.market == "US")
        ).all()
        total = len(rows)
        ok = 0
        skipped = 0
        errors: list[tuple[str, str]] = []

        for i, (company_id, cik) in enumerate(rows, 1):
            if not cik:
                skipped += 1
                continue
            try:
                data = fetch_company_facts(cik.lstrip("0") or "0")
                if not data:
                    skipped += 1
                    continue
                parse_and_store_facts(db, company_id, data)
                ok += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append((company_id, str(e)[:200]))
                log.exception("SEC backfill failed for %s (cik=%s)", company_id, cik)

            if i % log_every == 0:
                log.info("进度 %d/%d (ok=%d, skipped=%d, errors=%d)", i, total, ok, skipped, len(errors))

        return {
            "total": total,
            "ok": ok,
            "skipped": skipped,
            "errors": errors,
        }
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()
    result = backfill_all_us()
    elapsed = time.time() - t0
    print(f"\n耗时 {elapsed:.1f}s ({elapsed/result['total']:.2f}s/家)")
    print(f"total={result['total']} ok={result['ok']} skipped={result['skipped']} errors={len(result['errors'])}")
    if result["errors"]:
        print("前 5 个错误:")
        for cid, msg in result["errors"][:5]:
            print(f"  {cid}: {msg}")
