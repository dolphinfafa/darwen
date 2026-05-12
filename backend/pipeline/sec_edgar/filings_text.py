# -*- coding: utf-8 -*-
"""SEC filing 元数据补全 + 原文下载（M1.9）。

依赖 submissions.json 已含的字段（acceptanceDateTime / items / primaryDocDescription），
补全 filing 表的 accepted_at / title，并下载 8-K / 10-K / 10-Q 原文到 text_document。

为 M4 AI 风险层提供真实法定披露证据，覆盖 PRD R5（审计）/ R6（监管/处罚）/ R10
（管理层稳定性）等需要文本判定的标签。

数据量考虑：
- 8-K 较短（30-200 KB HTML），全文截断 8000 字符存
- 10-K 巨大（5+ MB），只取 Item 1A (Risk Factors) 简化抽取（首段后 8000 字符）
- 10-Q 中等（500 KB-2 MB），抽 Part II Item 1 (Legal Proceedings)

只处理 form ∈ {8-K, 10-K, 10-Q}，其它表单（4 / 144 / SC 13G 等）跳过。
默认每家公司每次最多 ingest 30 份最近 filing 文本。
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.filing import Filing
from backend.models.text_document import TextDocument
from backend.pipeline.sec_edgar.rate_limiter import sec_get

log = logging.getLogger(__name__)


TEXT_FORMS = frozenset({"8-K", "10-K", "10-Q"})

# 各表单截断长度（字符）— 兼顾上下文窗口与存储成本
MAX_TEXT_LEN = {
    "8-K": 8000,
    "10-K": 8000,
    "10-Q": 6000,
}


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _filing_url(cik: str, acc_no: str, primary_doc: str) -> str:
    """构造 filing primary document URL."""
    cik_no_pad = cik.lstrip("0") or "0"
    acc_no_dash = acc_no.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/{primary_doc}"


def _filing_index_url(cik: str, acc_no: str) -> str:
    """构造 filing index 页 URL（含全部文件清单）。"""
    cik_no_pad = cik.lstrip("0") or "0"
    acc_no_dash = acc_no.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/"


def _build_title(form_type: str, items: str, primary_desc: str, filed_date: Optional[date]) -> str:
    """组合 filing 标题（仅 8-K 的 items 代码有标题语义）。"""
    parts = [form_type or ""]
    if primary_desc and primary_desc != form_type:
        parts.append(primary_desc)
    if items:
        parts.append(f"Items {items}")
    if filed_date:
        parts.append(filed_date.isoformat())
    return " · ".join(p for p in parts if p)


def enrich_filing_metadata(
    db: Session,
    company_id: str,
    cik: str,
    submissions_data: dict,
) -> int:
    """补全 filing 表的 accepted_at / title / url_pdf / 8-K items 元数据。

    对已存在的 filing 行 update；不存在的 filing 在此创建（避免 ingest text_document
    时 FK 失败）。返回 update + insert 总行数。
    """
    recent = submissions_data.get("filings", {}).get("recent", {})
    accs = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filed = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    items_list = recent.get("items", [])
    primary_descs = recent.get("primaryDocDescription", [])
    primary_docs = recent.get("primaryDocument", [])

    affected = 0
    n = min(len(accs), 200)
    for j in range(n):
        acc_no = accs[j]
        filing_id = f"SEC_{acc_no.replace('-', '')}"

        form_type = forms[j] if j < len(forms) else None
        filed_date = None
        if j < len(filed) and filed[j]:
            try:
                filed_date = date.fromisoformat(filed[j])
            except ValueError:
                pass
        accepted_dt = _parse_dt(accepted[j] if j < len(accepted) else "")
        items = items_list[j] if j < len(items_list) else ""
        primary_desc = primary_descs[j] if j < len(primary_descs) else ""
        primary_doc = primary_docs[j] if j < len(primary_docs) else ""

        url = _filing_url(cik, acc_no, primary_doc) if primary_doc else None
        title = _build_title(form_type, items, primary_desc, filed_date)
        actual_date = accepted_dt.date() if accepted_dt else filed_date

        row = db.get(Filing, filing_id)
        if row is None:
            db.add(Filing(
                filing_id=filing_id,
                company_id=company_id,
                source_type="SEC",
                form_type=form_type,
                title=title,
                filed_date=filed_date,
                accepted_at=accepted_dt,
                actual_disclosure_date=actual_date,
                available_date=filed_date,
                url=url,
                url_pdf=url,
            ))
        else:
            row.accepted_at = accepted_dt
            row.actual_disclosure_date = actual_date
            row.title = title
            if primary_doc:
                row.url_pdf = url
            if form_type and not row.form_type:
                row.form_type = form_type
        affected += 1
    db.commit()
    return affected


# ---------------- 原文下载 ----------------

def _fetch_html(url: str) -> Optional[str]:
    """通过现有 sec_get 拉取 HTML（已经走 rate limiter + User-Agent）。

    sec_get 期待相对 path；这里 URL 已是绝对，本函数手动用 httpx 直连
    但仍尊重 rate_limiter（导入复用）。
    """
    from backend.pipeline.sec_edgar.rate_limiter import sec_get_raw  # 见下
    try:
        return sec_get_raw(url)
    except Exception as e:  # noqa: BLE001
        log.warning("fetch_html failed %s: %s", url, e)
        return None


def _html_to_text(html: str) -> str:
    """简单 strip HTML → 纯文本，多空白合并。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "table"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…[truncated]"


def _extract_risk_factors(text: str, max_len: int) -> str:
    """从 10-K 文本中尝试抽取 Item 1A Risk Factors 段。

    简单启发式：找 "Item 1A" / "Risk Factors" 标题，取其后 max_len 字符。
    """
    lower = text.lower()
    for marker in ("item 1a. risk factors", "item 1a risk factors", "risk factors"):
        idx = lower.find(marker)
        if idx >= 0:
            return _truncate(text[idx : idx + max_len + 2000], max_len)
    # 找不到：截首部
    return _truncate(text, max_len)


def ingest_text_documents(
    db: Session,
    company_id: str,
    cik: str,
    submissions_data: dict,
    *,
    limit_per_form: dict[str, int] | None = None,
) -> dict:
    """下载 8-K / 10-K / 10-Q 原文写入 text_document。

    limit_per_form: 每种 form 最多 ingest 多少份（按 acceptanceDateTime desc）。
    默认 8-K=20, 10-K=2, 10-Q=4。
    """
    if limit_per_form is None:
        limit_per_form = {"8-K": 20, "10-K": 2, "10-Q": 4}

    recent = submissions_data.get("filings", {}).get("recent", {})
    accs = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filed = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    primary_docs = recent.get("primaryDocument", [])
    primary_descs = recent.get("primaryDocDescription", [])
    items_list = recent.get("items", [])

    form_counts: dict[str, int] = {f: 0 for f in TEXT_FORMS}
    inserted = 0
    skipped_existing = 0
    failures = 0

    n = min(len(accs), 200)
    for j in range(n):
        form_type = forms[j] if j < len(forms) else None
        if form_type not in TEXT_FORMS:
            continue
        if form_counts[form_type] >= limit_per_form.get(form_type, 0):
            continue

        acc_no = accs[j]
        filing_id = f"SEC_{acc_no.replace('-', '')}"
        primary_doc = primary_docs[j] if j < len(primary_docs) else ""
        if not primary_doc or not primary_doc.lower().endswith((".htm", ".html", ".txt")):
            continue

        # 去重：同一 filing_id 不重复 ingest
        existing = db.execute(
            select(TextDocument.doc_id).where(
                and_(
                    TextDocument.filing_id == filing_id,
                    TextDocument.doc_type == form_type,
                )
            ).limit(1)
        ).first()
        if existing:
            skipped_existing += 1
            form_counts[form_type] += 1
            continue

        url = _filing_url(cik, acc_no, primary_doc)
        html = _fetch_html(url)
        if html is None:
            failures += 1
            continue

        text = _html_to_text(html)
        max_len = MAX_TEXT_LEN.get(form_type, 8000)
        if form_type == "10-K":
            text = _extract_risk_factors(text, max_len)
        else:
            text = _truncate(text, max_len)

        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        accepted_dt = _parse_dt(accepted[j] if j < len(accepted) else "")
        filed_date = None
        if j < len(filed) and filed[j]:
            try:
                filed_date = date.fromisoformat(filed[j])
            except ValueError:
                pass
        primary_desc = primary_descs[j] if j < len(primary_descs) else ""
        items = items_list[j] if j < len(items_list) else ""

        db.add(TextDocument(
            company_id=company_id,
            source_type="SEC",
            doc_type=form_type,
            title=_build_title(form_type, items, primary_desc, filed_date),
            content_text=text,
            content_url=url,
            content_sha256=sha,
            published_at=accepted_dt or (datetime.combine(filed_date, datetime.min.time()) if filed_date else None),
            filing_id=filing_id,
        ))
        inserted += 1
        form_counts[form_type] += 1

    db.commit()
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "failures": failures,
        "by_form": form_counts,
    }


# ---------------- 顶层入口 ----------------

def enrich_company_filings(
    db: Session,
    company_id: str,
    cik: str,
    *,
    limit_per_form: dict[str, int] | None = None,
) -> dict:
    """对单家公司：补 filing 元数据 + 下载 8-K/10-K/10-Q 原文。"""
    from backend.pipeline.sec_edgar.submissions import fetch_submission
    data = fetch_submission(cik)
    if not data:
        return {"error": "submissions empty"}
    updated_meta = enrich_filing_metadata(db, company_id, cik, data)
    text_stats = ingest_text_documents(db, company_id, cik, data, limit_per_form=limit_per_form)
    return {
        "updated_filing_metadata": updated_meta,
        **text_stats,
    }


def enrich_all_us(
    *,
    limit_per_form: dict[str, int] | None = None,
    log_every: int = 20,
    company_ids: list[str] | None = None,
) -> dict:
    db = SessionLocal()
    try:
        if company_ids is None:
            rows = db.execute(
                select(Company.company_id, Company.cik).where(Company.market == "US")
            ).all()
        else:
            rows = db.execute(
                select(Company.company_id, Company.cik).where(Company.company_id.in_(company_ids))
            ).all()

        total = len(rows)
        ok = 0
        total_inserted = 0
        total_meta_updated = 0
        errors: list[tuple[str, str]] = []
        for i, (cid, cik) in enumerate(rows, 1):
            if not cik:
                continue
            try:
                stats = enrich_company_filings(db, cid, cik.lstrip("0") or "0", limit_per_form=limit_per_form)
                if "error" in stats:
                    errors.append((cid, stats["error"]))
                    continue
                ok += 1
                total_inserted += stats.get("inserted", 0)
                total_meta_updated += stats.get("updated_filing_metadata", 0)
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append((cid, str(e)[:200]))
                log.exception("enrich failed for %s", cid)
            if i % log_every == 0:
                log.info("进度 %d/%d  ok=%d  text_inserted=%d  meta_updated=%d  errs=%d",
                         i, total, ok, total_inserted, total_meta_updated, len(errors))

        return {
            "total": total, "ok": ok,
            "text_inserted": total_inserted,
            "meta_updated": total_meta_updated,
            "errors": errors,
        }
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="SEC filing 文本与元数据增强")
    parser.add_argument("--company", action="append", help="指定 company_id（可多次）")
    parser.add_argument("--limit-8k", type=int, default=20)
    parser.add_argument("--limit-10k", type=int, default=2)
    parser.add_argument("--limit-10q", type=int, default=4)
    args = parser.parse_args()

    limit_per_form = {"8-K": args.limit_8k, "10-K": args.limit_10k, "10-Q": args.limit_10q}
    res = enrich_all_us(limit_per_form=limit_per_form, company_ids=args.company)
    summary = {k: v for k, v in res.items() if k != "errors"}
    summary["error_count"] = len(res["errors"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if res["errors"]:
        print("\n前 5 个错误:")
        for cid, msg in res["errors"][:5]:
            print(f"  {cid}: {msg}")
