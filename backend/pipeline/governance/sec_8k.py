# -*- coding: utf-8 -*-
"""从美股 SEC 8-K 提取治理硬事实信号 → governance_signal。

text_document 中 8-K 的 title 已结构化标注 Item 编号（如「8-K · Items 5.02 · 2026-05-11」），
无需解析正文，直接按 Item 映射治理信号：

- Item 4.02 → restatement   财务重述（非依赖性结论，前期财报不可信）── hard 红旗
- Item 4.01 → auditor_change 审计师更换 ── soft
- Item 5.02 → exec_departure 高管/董事离任·任命 ── info（计数型，由风险层聚合判定不稳定）

event_date 取 published_at（点时可见性基准）。幂等：signal_id = hash(company_id+type+doc_id)。
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.text_document import TextDocument
from backend.models.governance_signal import GovernanceSignal

# Item → (signal_type, severity, detail)
ITEM_MAP: dict[str, tuple[str, str, str]] = {
    "4.02": ("restatement", "hard", "财务重述：8-K Item 4.02 非依赖性结论，前期财报不可信"),
    "4.01": ("auditor_change", "soft", "审计师更换：8-K Item 4.01"),
    "5.02": ("exec_departure", "info", "高管/董事离任或任命：8-K Item 5.02"),
}

_RE_ITEMS = re.compile(r"Items?\s+([\d.,\s]+)")


def _sig_id(company_id: str, stype: str, doc_id: str) -> str:
    return hashlib.sha256(f"{company_id}_{stype}_{doc_id}".encode()).hexdigest()[:64]


def backfill_8k_governance_signals(db: Session) -> tuple[int, dict[str, int]]:
    """扫描全部 8-K，提取治理信号入 governance_signal（幂等）。返回 (新增数, 按类型计数)。"""
    rows = db.execute(
        select(
            TextDocument.doc_id, TextDocument.company_id,
            TextDocument.title, TextDocument.published_at,
        ).where(TextDocument.doc_type == "8-K")
    ).all()

    existing = set(db.execute(select(GovernanceSignal.signal_id)).scalars())
    new_objs: list[GovernanceSignal] = []
    n_by: dict[str, int] = {}

    for doc_id, company_id, title, published_at in rows:
        if not title or not company_id or published_at is None:
            continue
        m = _RE_ITEMS.search(title)
        if not m:
            continue
        event_date = published_at.date()
        items = {x.strip() for x in m.group(1).replace(" ", ",").split(",") if x.strip()}
        for item in items:
            mapping = ITEM_MAP.get(item)
            if not mapping:
                continue
            stype, sev, detail = mapping
            sid = _sig_id(company_id, stype, doc_id)
            if sid in existing:
                continue
            existing.add(sid)
            new_objs.append(GovernanceSignal(
                signal_id=sid, company_id=company_id, signal_type=stype,
                severity=sev, event_date=event_date, value=None,
                detail=detail, source_type="SEC-8K", source_doc_id=doc_id,
            ))
            n_by[stype] = n_by.get(stype, 0) + 1

    if new_objs:
        db.add_all(new_objs)
        db.commit()
    return len(new_objs), n_by
