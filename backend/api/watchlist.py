# -*- coding: utf-8 -*-
"""我的股票池 watchlist API：增删改查 + 详情页"进入股票池"便捷入口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.company import Company
from backend.models.security import Security
from backend.models.user import User
from backend.models.watchlist import Watchlist, WatchlistItem
from backend.schemas.v2 import (
    AddToWatchlistRequest,
    WatchlistCreateRequest,
    WatchlistDetailResponse,
    WatchlistItemAddRequest,
    WatchlistItemOut,
    WatchlistRenameRequest,
    WatchlistSummary,
)
from backend.services.auth import get_current_user

router = APIRouter(prefix="/v2", tags=["watchlist"])


def _summary(db: Session, wl: Watchlist) -> WatchlistSummary:
    cnt = db.scalar(
        select(func.count(WatchlistItem.id)).where(WatchlistItem.watchlist_id == wl.id)
    ) or 0
    return WatchlistSummary(
        id=wl.id, name=wl.name, item_count=cnt,
        created_at=wl.created_at, updated_at=wl.updated_at,
    )


def _owned(db: Session, wid: int, user: User) -> Watchlist:
    wl = db.get(Watchlist, wid)
    if wl is None:
        raise HTTPException(404, "watchlist not found")
    if wl.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "not your watchlist")
    return wl


@router.get("/watchlists", response_model=list[WatchlistSummary])
def list_watchlists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wls = db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at)
    ).scalars().all()
    return [_summary(db, w) for w in wls]


@router.post("/watchlists", response_model=WatchlistSummary)
def create_watchlist(body: WatchlistCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = Watchlist(user_id=user.id, name=body.name.strip())
    db.add(wl); db.commit(); db.refresh(wl)
    return _summary(db, wl)


@router.patch("/watchlists/{wid}", response_model=WatchlistSummary)
def rename_watchlist(wid: int, body: WatchlistRenameRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = _owned(db, wid, user)
    wl.name = body.name.strip()
    db.add(wl); db.commit(); db.refresh(wl)
    return _summary(db, wl)


@router.delete("/watchlists/{wid}")
def delete_watchlist(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = _owned(db, wid, user)
    db.execute(delete(WatchlistItem).where(WatchlistItem.watchlist_id == wid))
    db.delete(wl); db.commit()
    return {"ok": True}


@router.get("/watchlists/{wid}", response_model=WatchlistDetailResponse)
def get_watchlist(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = _owned(db, wid, user)
    rows = db.execute(
        select(WatchlistItem, Company, Security)
        .join(Company, WatchlistItem.company_id == Company.company_id)
        .join(Security, Security.company_id == Company.company_id, isouter=True)
        .where(WatchlistItem.watchlist_id == wid)
        .order_by(WatchlistItem.added_at.desc())
    ).all()
    seen: set[str] = set()
    items: list[WatchlistItemOut] = []
    for it, c, sec in rows:
        if it.company_id in seen:
            continue
        seen.add(it.company_id)
        items.append(WatchlistItemOut(
            company_id=it.company_id,
            ticker=(sec.ticker if sec else (c.stock_code or c.cik)),
            name=c.name, market=c.market, industry_name=c.industry_name,
            note=it.note, source_run_id=it.source_run_id, added_at=it.added_at,
        ))
    return WatchlistDetailResponse(id=wl.id, name=wl.name, items=items)


@router.post("/watchlists/{wid}/items")
def add_item(wid: int, body: WatchlistItemAddRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = _owned(db, wid, user)
    if db.get(Company, body.company_id) is None:
        raise HTTPException(404, "company not found")
    exists = db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl.id, WatchlistItem.company_id == body.company_id
        ).limit(1)
    ).scalar()
    if exists:
        return {"ok": True, "already": True}
    db.add(WatchlistItem(watchlist_id=wl.id, company_id=body.company_id,
                         source_run_id=body.source_run_id, note=body.note))
    db.commit()
    return {"ok": True}


@router.delete("/watchlists/{wid}/items/{company_id}")
def remove_item(wid: int, company_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned(db, wid, user)
    db.execute(delete(WatchlistItem).where(
        WatchlistItem.watchlist_id == wid, WatchlistItem.company_id == company_id
    ))
    db.commit()
    return {"ok": True}


@router.post("/watchlists/add-company", response_model=WatchlistSummary)
def add_company_to_watchlist(body: AddToWatchlistRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """详情页"进入我的股票池"：指定 watchlist_id，或给名字自动建/复用，或落默认池。"""
    if db.get(Company, body.company_id) is None:
        raise HTTPException(404, "company not found")
    if body.watchlist_id is not None:
        wl = _owned(db, body.watchlist_id, user)
    else:
        name = (body.watchlist_name or "我的股票池").strip()
        wl = db.execute(
            select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.name == name).limit(1)
        ).scalar()
        if wl is None:
            wl = Watchlist(user_id=user.id, name=name)
            db.add(wl); db.commit(); db.refresh(wl)
    exists = db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl.id, WatchlistItem.company_id == body.company_id
        ).limit(1)
    ).scalar()
    if not exists:
        db.add(WatchlistItem(watchlist_id=wl.id, company_id=body.company_id,
                             source_run_id=body.source_run_id, note=body.note))
        db.commit()
    return _summary(db, wl)
