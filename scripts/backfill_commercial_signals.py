# -*- coding: utf-8 -*-
"""阶段3：一次性回填商业深度风险信号（客户/供应商集中度 + segment HHI）。

- 美股：从完整 10-K（含 iXBRL）抽取，写 metric_periodic(commercial_v1) + governance_signal。
- A股：Tushare fina_mainbz 主营构成算 segment HHI，写 metric_periodic(commercial_v1)。
  （A股客户/供应商集中度无免费结构化数据，详见 prd 采购建议，本期不实现。）

幂等，可重复执行。用法：python -m scripts.backfill_commercial_signals
"""
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

from backend.database import SessionLocal
from backend.pipeline.commercial.sec_commercial import backfill_commercial_signals
from backend.pipeline.commercial.tushare_segment import backfill_cn_segment_hhi

db = SessionLocal()
try:
    print(">>> 美股 10-K 商业信号抽取…", flush=True)
    us = backfill_commercial_signals(db)
    print(json.dumps({"US": us}, indent=2, ensure_ascii=False), flush=True)

    print(">>> A股 segment HHI（Tushare fina_mainbz）…", flush=True)
    cn = backfill_cn_segment_hhi(db)
    print(json.dumps({"CN_A": cn}, indent=2, ensure_ascii=False), flush=True)
finally:
    db.close()
