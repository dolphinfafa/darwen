# -*- coding: utf-8 -*-
"""A股扩池后下游全量回填——让新入库的 A股立即可进三层漏斗。

顺序（依赖关系）：
1. **指标预计算** `persist_all_metrics_bulk`（全部 CN_A）：ROCE / 杠杆 / 现金质量 / 风险(应计·FCF波动) /
   偿付(Altman Z·营运资本·CCC) / 稀释 / 估值 → metric_periodic。
2. **行业 peer 重建** `compute_industry_peer_stats`（全市场）：新增 A股大幅提升同行业样本数，
   原先因样本 <5 跳过的行业现可计相对值。
3. **治理硬事实** `ingest_pledge_signals` + `ingest_manager_changes`（自动遍历全部 CN 公司）。
4. **商业 segment HHI** `backfill_cn_segment_hhi`（Tushare fina_mainbz，全部 CN_A）。

用法：python -m scripts.backfill_cn_downstream
"""
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

from sqlalchemy import select
from backend.database import SessionLocal
from backend.models.company import Company
from backend.metrics.compute import persist_all_metrics_bulk
from backend.metrics.industry_peer import compute_industry_peer_stats
from backend.pipeline.governance.tushare_gov import ingest_pledge_signals, ingest_manager_changes
from backend.pipeline.commercial.tushare_segment import backfill_cn_segment_hhi


def main():
    db = SessionLocal()
    try:
        cn_ids = [r[0] for r in db.execute(
            select(Company.company_id).where(Company.market == "CN_A")
        ).all()]
        print(f">>> 1/4 指标预计算（{len(cn_ids)} 家 CN_A）…", flush=True)
        m = persist_all_metrics_bulk(company_ids=cn_ids)
        print(json.dumps({"metrics": {k: v for k, v in m.items() if k != "errors"},
                          "metric_errors": len(m.get("errors", []))}, ensure_ascii=False), flush=True)

        print(">>> 2/4 行业 peer 重建（全市场）…", flush=True)
        n_co, n_grp = compute_industry_peer_stats(db)
        print(json.dumps({"industry_peer": {"companies": n_co, "valid_groups": n_grp}}, ensure_ascii=False), flush=True)

        print(">>> 3/4 治理硬事实（质押 + 管理层）…", flush=True)
        pl_new, pl_co = ingest_pledge_signals(db)
        mg_new, mg_co = ingest_manager_changes(db)
        print(json.dumps({"pledge": {"new": pl_new, "companies": pl_co},
                          "managers": {"new": mg_new, "companies": mg_co}}, ensure_ascii=False), flush=True)

        print(">>> 4/4 商业 segment HHI（fina_mainbz）…", flush=True)
        seg = backfill_cn_segment_hhi(db)
        print(json.dumps({"segment_hhi": seg}, ensure_ascii=False), flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
