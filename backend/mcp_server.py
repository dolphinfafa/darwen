# -*- coding: utf-8 -*-
"""Darwen MCP server（streamable HTTP）：外部 agent 凭 MCP 令牌读「我的股票池」行情。

挂载在 FastAPI 的 /v2/mcp（经 nginx /darwen/v2/ 暴露）。鉴权用纯 ASGI 中间件读
Authorization: Bearer <token> → 反查用户 → 存入 contextvar；工具按 contextvar 取用户。
"""
from __future__ import annotations

import contextvars
from datetime import date

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from starlette.responses import JSONResponse

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.security import Security
from backend.models.watchlist import Watchlist, WatchlistItem
from backend.services.mcp_auth import resolve_user_by_token

_current_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "mcp_user_id", default=None
)

mcp = FastMCP(
    "darwen-watchlist",
    instructions="读取用户「我的股票池」每只股票的最新收盘价与市盈率(TTM)，用于判断是否跌到目标买入价。",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def list_watchlist_quotes() -> list[dict]:
    """读取你「我的股票池」中每只股票的最新收盘价与市盈率(TTM)。

    用于判断股价是否已跌到你满意的买入价位。每只返回：
    ticker（代码）、name（名称）、market（US/CN_A）、industry（行业）、
    currency（USD/CNY）、latest_close（最新收盘价）、
    latest_trade_date（该价对应的交易日，据此判断价格新旧）、pe_ttm（滚动 12 个月市盈率）。
    价格为按需拉取的最近交易日收盘价。
    """
    uid = _current_user_id.get()
    if uid is None:
        raise ValueError("未鉴权：缺少有效的 MCP 令牌")

    from backend.services.quote import refresh_quotes
    from backend.metrics.valuation import compute_valuation_snapshot

    db = SessionLocal()
    try:
        rows = db.execute(
            select(WatchlistItem, Company, Security)
            .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
            .join(Company, WatchlistItem.company_id == Company.company_id)
            .join(Security, Security.company_id == Company.company_id, isouter=True)
            .where(Watchlist.user_id == uid)
            .order_by(WatchlistItem.added_at.desc())
        ).all()

        refresh_quotes(db, [it.company_id for it, _c, _s in rows])

        today = date.today()
        seen: set[str] = set()
        out: list[dict] = []
        for it, c, sec in rows:
            if it.company_id in seen:
                continue
            seen.add(it.company_id)
            close = td = pe = None
            try:
                snap = compute_valuation_snapshot(db, it.company_id, today, market=c.market)
                close, td, pe = snap.latest_close, snap.latest_trade_date, snap.pe_ttm
            except Exception:  # noqa: BLE001
                pass
            out.append({
                "ticker": (sec.ticker if sec else (c.stock_code or c.cik)),
                "name": c.name,
                "market": c.market,
                "industry": c.industry_name,
                "currency": "USD" if c.market == "US" else "CNY",
                "latest_close": close,
                "latest_trade_date": td.isoformat() if td else None,
                "pe_ttm": round(pe, 2) if pe is not None else None,
            })
        return out
    finally:
        db.close()


class _McpAuthASGI:
    """纯 ASGI 鉴权中间件：Bearer 令牌 → 用户 → contextvar（同 task，工具可读）。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        db = SessionLocal()
        try:
            user = resolve_user_by_token(db, token)
        finally:
            db.close()
        if user is None:
            resp = JSONResponse({"error": "invalid or missing MCP token"}, status_code=401)
            return await resp(scope, receive, send)
        ctx = _current_user_id.set(user.id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(ctx)


def build_mcp_app():
    """返回带鉴权的 MCP ASGI app，供 FastAPI mount。"""
    return _McpAuthASGI(mcp.streamable_http_app())
