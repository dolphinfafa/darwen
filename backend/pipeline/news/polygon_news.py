# -*- coding: utf-8 -*-
"""Polygon News 拉取（M1.10，PRD 第 6 节"新闻"证据源）。

输入：美股 ticker
输出：写入 text_document(source_type='PG-NEWS', doc_type='news')

PRD 第 6 节证据优先级：
    法定披露 > 巨潮公告 > 供应商结构化公告 > **主流新闻** > 管理层采访
新闻最高只能给 REVIEW（不能 REJECT）。

API: GET /v2/reference/news?ticker=AAPL&limit=50&apiKey=...
返回每条含 id / publisher / title / description / published_utc / article_url / tickers / keywords。
description 是新闻摘要（200-2000 字符），content_text 直接存。

去重：按 article_url 唯一（同一新闻可能被多次拉到）。
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.security import Security
from backend.models.text_document import TextDocument


log = logging.getLogger(__name__)


# 用户环境 .env 写的 S3 endpoint 是 files.massive.com（Polygon 镜像）；
# REST API 两个 host 都 work，优先官方
DEFAULT_BASE_URL = "https://api.polygon.io"
NEWS_PATH = "/v2/reference/news"

# Polygon API 速率：付费版无限制；免费版 5 req/min
DEFAULT_RPS = 8.0
DEFAULT_TIMEOUT = 15.0


_settings = get_settings()
_client = httpx.Client(timeout=DEFAULT_TIMEOUT)
_last_call = 0.0


def _throttle(rps: float = DEFAULT_RPS):
    """简单速率限制。"""
    global _last_call
    min_interval = 1.0 / rps
    now = time.monotonic()
    elapsed = now - _last_call
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_call = time.monotonic()


def fetch_news(
    ticker: str,
    *,
    limit: int = 50,
    published_after: Optional[date] = None,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> list[dict]:
    """拉单只 ticker 的最近 limit 条新闻（最多 1000）。"""
    api_key = api_key or _settings.polygon_api_key
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY 未配置")

    params = {
        "ticker": ticker,
        "limit": min(limit, 1000),
        "order": "desc",
        "sort": "published_utc",
        "apiKey": api_key,
    }
    if published_after:
        params["published_utc.gte"] = published_after.isoformat()

    _throttle()
    try:
        resp = _client.get(f"{base_url}{NEWS_PATH}", params=params)
    except httpx.HTTPError as e:
        log.warning("polygon news fetch failed for %s: %s", ticker, e)
        return []
    if resp.status_code == 429:
        time.sleep(2.0)
        _throttle()
        resp = _client.get(f"{base_url}{NEWS_PATH}", params=params)
    if resp.status_code != 200:
        log.warning("polygon news %s status=%d body=%s", ticker, resp.status_code, resp.text[:200])
        return []
    return resp.json().get("results", []) or []


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def ingest_news_for_company(
    db: Session,
    company_id: str,
    ticker: str,
    *,
    limit: int = 50,
    published_after: Optional[date] = None,
) -> dict:
    """对单家公司拉新闻并 ingest 到 text_document。按 content_url 去重。"""
    items = fetch_news(ticker, limit=limit, published_after=published_after)
    if not items:
        return {"fetched": 0, "inserted": 0, "skipped_existing": 0}

    # 一次性查已有 url 集合避免 N 次查询
    existing_urls = set(
        r[0]
        for r in db.execute(
            select(TextDocument.content_url).where(
                and_(
                    TextDocument.company_id == company_id,
                    TextDocument.source_type == "PG-NEWS",
                )
            )
        ).all()
    )

    inserted = 0
    skipped = 0
    for item in items:
        url = item.get("article_url") or ""
        if not url:
            continue
        if url in existing_urls:
            skipped += 1
            continue

        title = (item.get("title") or "")[:500]
        description = item.get("description") or ""
        # description 本身一般 < 2000；再叠加 keywords 与 publisher 元数据
        publisher = (item.get("publisher") or {}).get("name", "")
        keywords = item.get("keywords") or []
        kw_str = ",".join(keywords[:8]) if keywords else ""
        tickers_str = ",".join(item.get("tickers") or [])[:200]

        content = description.strip()
        if kw_str:
            content = f"[publisher={publisher} | tickers={tickers_str} | keywords={kw_str}]\n\n{content}"

        # 截断到 4KB
        if len(content) > 4000:
            content = content[:4000] + "…[truncated]"

        sha = hashlib.sha256((url + content[:200]).encode("utf-8")).hexdigest()
        published_at = _parse_dt(item.get("published_utc"))

        db.add(TextDocument(
            company_id=company_id,
            source_type="PG-NEWS",
            doc_type="news",
            title=title,
            content_text=content,
            content_url=url,
            content_sha256=sha,
            published_at=published_at,
            filing_id=None,
        ))
        existing_urls.add(url)
        inserted += 1

    db.commit()
    return {
        "fetched": len(items),
        "inserted": inserted,
        "skipped_existing": skipped,
    }


def ingest_all_us(
    *,
    limit_per_ticker: int = 30,
    published_after: Optional[date] = None,
    log_every: int = 25,
    company_ids: Optional[list[str]] = None,
) -> dict:
    """批量拉取美股新闻。company_ids=None 则全部美股。"""
    db = SessionLocal()
    try:
        q = select(Company.company_id, Security.ticker).join(
            Security, Security.company_id == Company.company_id
        ).where(Company.market == "US")
        if company_ids is not None:
            q = q.where(Company.company_id.in_(company_ids))
        # 每 company 取首个 ticker
        seen: set[str] = set()
        pairs: list[tuple[str, str]] = []
        for cid, tk in db.execute(q.order_by(Company.company_id, Security.security_id)).all():
            if cid in seen:
                continue
            seen.add(cid)
            pairs.append((cid, tk))

        total = len(pairs)
        ok = 0
        agg_inserted = 0
        agg_skipped = 0
        errors: list[tuple[str, str]] = []

        for i, (cid, tk) in enumerate(pairs, 1):
            try:
                stats = ingest_news_for_company(
                    db, cid, tk,
                    limit=limit_per_ticker, published_after=published_after,
                )
                ok += 1
                agg_inserted += stats["inserted"]
                agg_skipped += stats["skipped_existing"]
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append((cid, str(e)[:200]))
                log.exception("polygon news failed for %s (%s)", cid, tk)
            if i % log_every == 0:
                log.info("进度 %d/%d ok=%d inserted=%d skipped=%d errors=%d",
                         i, total, ok, agg_inserted, agg_skipped, len(errors))

        return {
            "total": total, "ok": ok,
            "news_inserted": agg_inserted,
            "skipped_existing": agg_skipped,
            "errors": errors,
        }
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Polygon 美股新闻拉取")
    parser.add_argument("--company", action="append", help="指定 company_id（可多次）")
    parser.add_argument("--limit", type=int, default=30, help="每个 ticker 拉取多少条")
    parser.add_argument("--after", default=None, help="只取该日期之后发布的（yyyy-mm-dd）")
    args = parser.parse_args()

    after = date.fromisoformat(args.after) if args.after else None
    res = ingest_all_us(
        limit_per_ticker=args.limit,
        published_after=after,
        company_ids=args.company,
    )
    summary = {k: v for k, v in res.items() if k != "errors"}
    summary["error_count"] = len(res["errors"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if res["errors"]:
        print("\n前 5 个错误:")
        for cid, msg in res["errors"][:5]:
            print(f"  {cid}: {msg}")
