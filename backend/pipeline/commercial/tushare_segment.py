# -*- coding: utf-8 -*-
"""A股 segment 收入 HHI（阶段3，零采购）——复用 Tushare fina_mainbz 主营构成。

A股客户/供应商集中度无任何免费结构化接口（详见文档采购建议），但**业务多元化**可免费量化：
`fina_mainbz`(type='P' 按产品/业务线) 给主营构成 bz_sales，去重后算 HHI=Σ(share²)。

落点与美股完全一致：写 metric_periodic（metric_name=segment_revenue_hhi / segment_count，
formula_version=commercial_v1），漏斗 `_eval_sturdiness` 按 metric 名跨市场统一消费，无需改动。

bz_item 分类有层级/重复（如「系列酒」与「其他酒系列」同值、多个「其他」兜底行），
清洗规则：剔除「其他/合计/小计/抵销/内部」兜底行 + 按金额去重相同层级 + 单业务线不计（保守跳过）。
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company

log = logging.getLogger(__name__)

FORMULA_VERSION = "commercial_v1"
MIN_SEGMENTS = 2  # 少于 2 个业务线不计 HHI（单一主业无法判多元化，保守跳过）
_EXCLUDE_ITEM = re.compile(r"其他|合计|小计|抵销|抵消|内部|分部间|未分配")


def _ts_code(company_id: str) -> str:
    code = company_id.replace("CN_", "")
    return f"{code}.SH" if code[:1] == "6" else f"{code}.SZ"


def _hhi_from_items(rows) -> tuple[Optional[float], int]:
    """从 (bz_item, bz_sales) 列表清洗算 HHI。返回 (hhi, n_segments)。"""
    items: dict[str, float] = {}
    seen_vals: set[int] = set()
    for name, sales in rows:
        if sales is None:
            continue
        try:
            v = float(sales)
        except (TypeError, ValueError):
            continue
        if v <= 0 or _EXCLUDE_ITEM.search(str(name or "")):
            continue
        key = int(round(v, -3))  # 金额近似去重（同值不同标签视为同一层级）
        if key in seen_vals:
            continue
        seen_vals.add(key)
        items[str(name)] = v
    if len(items) < MIN_SEGMENTS:
        return None, len(items)
    total = sum(items.values())
    if total <= 0:
        return None, len(items)
    return sum((v / total) ** 2 for v in items.values()), len(items)


def backfill_cn_segment_hhi(db: Session, *, years: tuple[int, int] = (2018, 2025)) -> dict:
    """对全部 A股公司，按年报期算 segment HHI 入 metric_periodic（commercial_v1，幂等）。"""
    from backend.metrics.compute import _upsert_metric
    from backend.pipeline.cn_stock_v2.tushare_client import get_pro

    pro = get_pro()
    cids = [r[0] for r in db.execute(
        select(Company.company_id).where(Company.market == "CN_A")
    ).all()]

    stat = {"companies": len(cids), "with_data": 0, "periods_written": 0, "failed": 0}
    for cid in cids:
        try:
            df = pro.fina_mainbz(ts_code=_ts_code(cid), type="P")
        except Exception as e:  # noqa: BLE001
            stat["failed"] += 1
            log.warning("fina_mainbz 失败 %s: %s", cid, str(e)[:120])
            continue
        if df is None or len(df) == 0:
            continue
        wrote_any = False
        # 仅年报期（end_date 以 1231 结尾），按期分组
        annuals = df[df["end_date"].astype(str).str.endswith("1231")]
        for end_str, grp in annuals.groupby("end_date"):
            y = int(str(end_str)[:4])
            if not (years[0] <= y <= years[1]):
                continue
            hhi, n = _hhi_from_items(zip(grp["bz_item"], grp["bz_sales"]))
            if hhi is None:
                continue
            pe = date(y, 12, 31)
            _upsert_metric(db, cid, pe, "segment_revenue_hhi", hhi, [], f"n_seg={n}",
                           formula_version=FORMULA_VERSION)
            _upsert_metric(db, cid, pe, "segment_count", float(n), [], None,
                           formula_version=FORMULA_VERSION)
            stat["periods_written"] += 1
            wrote_any = True
        if wrote_any:
            stat["with_data"] += 1
        db.commit()
    return stat


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = SessionLocal()
    try:
        print(json.dumps(backfill_cn_segment_hhi(db), indent=2, ensure_ascii=False))
    finally:
        db.close()
