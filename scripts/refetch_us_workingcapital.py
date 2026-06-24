# -*- coding: utf-8 -*-
"""阶段1b：重拉美股 SEC companyfacts，补营运资本明细 concept（幂等，只补新增字段）。

新增 concept：RetainedEarningsAccumulatedDeficit / AccountsReceivableNetCurrent /
InventoryNet / AccountsPayableCurrent / CostOfGoodsAndServicesSold / CostOfRevenue。
"""
import logging
logging.disable(logging.WARNING)

from sqlalchemy import select, text
from backend.database import SessionLocal
from backend.models.company import Company
from backend.pipeline.sec_edgar.company_facts import fetch_company_facts, parse_and_store_facts

db = SessionLocal()
ids = [r[0] for r in db.execute(select(Company.company_id).where(Company.market == "US")).all()]
print(f"美股公司 {len(ids)} 家，开始重拉营运资本字段…", flush=True)
ok = fail = 0
for i, cid in enumerate(ids):
    cik = cid[3:]  # 去 US_ 前缀，已是 10 位
    try:
        data = fetch_company_facts(cik)
        if data:
            parse_and_store_facts(db, cid, data)
            ok += 1
        else:
            fail += 1
    except Exception:
        fail += 1
        db.rollback()
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(ids)} ok={ok} fail={fail}", flush=True)

print(f"DONE ok={ok} fail={fail}", flush=True)
for c in ["RetainedEarningsAccumulatedDeficit", "AccountsReceivableNetCurrent",
          "InventoryNet", "AccountsPayableCurrent", "CostOfGoodsAndServicesSold", "CostOfRevenue"]:
    n = db.execute(text("SELECT COUNT(DISTINCT company_id) FROM fact WHERE source_type='SEC' AND concept=:c"), {"c": c}).scalar()
    print(f"  覆盖 {c}: {n}", flush=True)
