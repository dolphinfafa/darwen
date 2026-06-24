# -*- coding: utf-8 -*-
"""从 A股 Tushare 提取治理硬事实信号 → governance_signal（复用美股同一张表）。

- pledge_stat   控股股东/整体股权质押比例 → signal_type='share_pledge'（A股特有强治理红旗）
                按月去重存质押率快照，event_date=统计日；风险层取 ≤as_of 最新一期按 value 判 hard/soft。
- stk_managers  高管/董事离任（end_date 非空）→ signal_type='exec_departure'
                **复用美股 8-K Item 5.02 同一 signal_type**，风险层「近 3 年变动计数」逻辑零改动即支持 A股。

幂等：signal_id = hash(company_id+type+key)。
"""
from __future__ import annotations

import hashlib

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.governance_signal import GovernanceSignal
from backend.pipeline.cn_stock_v2.field_map import to_ts_code
from backend.pipeline.cn_stock_v2.tushare_client import get_pro, _parse_date


def _sig_id(company_id: str, stype: str, key: str) -> str:
    return hashlib.sha256(f"{company_id}_{stype}_{key}".encode()).hexdigest()[:64]


def _cn_companies(db: Session) -> list[tuple[str, str]]:
    return [
        (cid, code) for cid, code in db.execute(
            select(Company.company_id, Company.stock_code).where(Company.market == "CN_A")
        ).all() if code
    ]


def ingest_pledge_signals(db: Session) -> tuple[int, int]:
    """股权质押比例 → share_pledge（按月去重快照）。返回 (新增数, 覆盖公司数)。"""
    pro = get_pro()
    existing = set(db.execute(
        select(GovernanceSignal.signal_id).where(GovernanceSignal.signal_type == "share_pledge")
    ).scalars())
    new_objs: list[GovernanceSignal] = []
    covered = 0
    for company_id, code in _cn_companies(db):
        try:
            df = pro.pledge_stat(ts_code=to_ts_code(code))
        except Exception as e:
            logger.warning(f"{code} pledge_stat 失败: {e}")
            continue
        if df is None or df.empty:
            continue
        covered += 1
        df = df.copy()
        df["ym"] = df["end_date"].astype(str).str[:6]
        df = df.sort_values("end_date").drop_duplicates("ym", keep="last")
        for _, r in df.iterrows():
            ev = _parse_date(r["end_date"])
            if ev is None or pd.isna(r["pledge_ratio"]):
                continue
            ratio = float(r["pledge_ratio"])
            sid = _sig_id(company_id, "share_pledge", str(r["end_date"]))
            if sid in existing:
                continue
            existing.add(sid)
            new_objs.append(GovernanceSignal(
                signal_id=sid, company_id=company_id, signal_type="share_pledge",
                severity="info", event_date=ev, value=ratio,
                detail=f"整体股权质押比例 {ratio:.2f}%", source_type="TS-pledge",
            ))
    if new_objs:
        db.add_all(new_objs)
        db.commit()
    return len(new_objs), covered


# 仅核心一把手离任才算「重大变动」，对齐美股 8-K Item 5.02 性质
# （A股 stk_managers 含全部高管，且需排除「副」职——"副总经理"含"总经理"子串）
_CORE_TITLES = ("董事长", "总经理", "财务总监", "首席执行官", "首席财务官", "CEO", "CFO")


def ingest_manager_changes(db: Session) -> tuple[int, int]:
    """核心高管/董事离任（stk_managers end_date 非空 + 核心岗）→ exec_departure（复用美股 signal_type）。"""
    pro = get_pro()
    existing = set(db.execute(
        select(GovernanceSignal.signal_id).where(GovernanceSignal.signal_type == "exec_departure")
    ).scalars())
    new_objs: list[GovernanceSignal] = []
    covered = 0
    for company_id, code in _cn_companies(db):
        try:
            df = pro.stk_managers(ts_code=to_ts_code(code))
        except Exception as e:
            logger.warning(f"{code} stk_managers 失败: {e}")
            continue
        if df is None or df.empty:
            continue
        covered += 1
        for _, r in df.iterrows():
            ev = _parse_date(r.get("end_date"))
            if ev is None:  # 仍在任，不算离任事件
                continue
            title = str(r.get("title") or "")
            if "副" in title:  # 排除副职（"副总经理"含"总经理"子串）
                continue
            if not any(k in title for k in _CORE_TITLES):  # 仅核心一把手
                continue
            name = str(r.get("name") or "")
            sid = _sig_id(company_id, "exec_departure", f"{name}_{r['end_date']}")
            if sid in existing:
                continue
            existing.add(sid)
            new_objs.append(GovernanceSignal(
                signal_id=sid, company_id=company_id, signal_type="exec_departure",
                severity="info", event_date=ev, value=None,
                detail=f"{title}{name} 离任", source_type="TS-managers",
            ))
    if new_objs:
        db.add_all(new_objs)
        db.commit()
    return len(new_objs), covered
