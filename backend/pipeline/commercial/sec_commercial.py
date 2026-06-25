# -*- coding: utf-8 -*-
"""从美股完整 10-K 抽取商业深度风险信号（阶段3，零采购）。

原著「商业风险」四类之一：客户/供应商集中度、业务多元化。本模块从 SEC 10-K
**完整 HTML（含内联 XBRL）**抽取三类信号，落点对齐阶段 1-2 既有路径：

| 信号 | 落点 | metric/signal |
|------|------|---------------|
| 客户集中度（top1 客户占营收 %） | metric_periodic（commercial_v1） | top_customer_revenue_pct |
| segment 收入 HHI（业务多元化代理） | metric_periodic（commercial_v1） | segment_revenue_hhi / segment_count |
| 供应商集中度（sole/limited source 定性） | governance_signal | signal_type=supplier_concentration（soft） |

抽取策略：**iXBRL 结构化优先 → 文本正则兜底**（纯规则，零 LLM）。

iXBRL 关键映射（实测 AMD FY2025 验证）：
- 客户集中度：`us-gaap:ConcentrationRiskPercentage1` 事实，按 context 的
  `us-gaap:ConcentrationRiskByBenchmarkAxis` 维度筛 `RevenueFromContractWithCustomerMember`
  口径（排除 `AccountsReceivableMember`），取最大值即 top 客户占营收比。
- segment 营收：`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` 事实，
  context 同时带 `srt:ConsolidationItemsAxis=OperatingSegmentsMember` + `StatementBusinessSegmentsAxis`
  且仅此两轴（排除产品/地区细分），按分部成员聚合最新财年营收 → HHI=Σ(share²)。

注：完整 10-K HTML 不入库（仅取信号），通过 sec_get_raw 按 content_url 重拉。
"""
from __future__ import annotations

import hashlib
import logging
import re
import warnings
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.governance_signal import GovernanceSignal
from backend.models.text_document import TextDocument
from backend.pipeline.sec_edgar.rate_limiter import sec_get_raw

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
log = logging.getLogger(__name__)

FORMULA_VERSION = "commercial_v1"

# iXBRL 维度常量（小写）
_AXIS_SEG = "us-gaap:statementbusinesssegmentsaxis"
_AXIS_CONS = "srt:consolidationitemsaxis"
_MEMBER_OPSEG = "us-gaap:operatingsegmentsmember"
_AXIS_BENCHMARK = "us-gaap:concentrationriskbybenchmarkaxis"
# 营收口径基准成员（不同年代/模板用法不一，均接受；排除 AccountsReceivableMember 等）
_MEMBERS_REVENUE = frozenset({
    "us-gaap:revenuefromcontractwithcustomermember",
    "us-gaap:salesrevenuenetmember",
    "us-gaap:salesrevenuegoodsnetmember",
    "us-gaap:salesrevenueservicesnetmember",
})
_AXIS_RISK_TYPE = "us-gaap:concentrationriskbytypeaxis"
_MEMBER_CUSTOMER_RISK = "us-gaap:customerconcentrationriskmember"
_AXIS_MAJOR_CUSTOMERS = "srt:majorcustomersaxis"
# 非单一客户成员（合并客户群 / 销售渠道分类），会高估 top1 → 排除，避免误杀多客户公司。
# 实测命中——
#   合并群：fivelargestcustomers / twoutilitycustomers / tmoattandverizoncombined /
#           transunionequifaxandexperiancustomers / nocustomerotherthanwalmart
#   销售渠道（非客户）：channelpartners / directcustomers（Zscaler 渠道 vs 直销，非单一客户依赖）
_RE_AGGREGATE_CUSTOMER = re.compile(
    r"customers|combined|largest|nocustomer|allcustomer|othercustomer|"
    r"two|three|four|five|six|seven|eight|nine|ten|"
    r"channel|distributor|reseller|partner|indirect|directcustomer", re.I
)
_SEG_REVENUE_CONCEPTS = (
    "us-gaap:revenuefromcontractwithcustomerexcludingassessedtax",
    "us-gaap:revenuefromcontractwithcustomerincludingassessedtax",
    "us-gaap:revenues",
)
# 排除的分部成员（公司/抵消/对账项，非真实经营分部）
_SEG_MEMBER_EXCLUDE = re.compile(
    r"corporate|elimination|intersegment|reconcil|other.*adjust|allother", re.I
)

# 供应商集中度定性短语（美股极少披露采购占比数字 → 仅定性 soft 旗标）
_SUPPLIER_PATTERNS = re.compile(
    r"sole supplier|single source|single supplier|sole source|"
    r"limited number of suppliers|a single (?:vendor|manufacturer)|"
    r"depend(?:s|ent)? on a limited number of (?:suppliers|vendors)",
    re.I,
)

# 客户集中度文本兜底
_RE_NO_CUSTOMER = re.compile(
    r"no (?:single |individual )?customer (?:accounted for|represented|exceeded|comprised).{0,40}?10\s?%",
    re.I,
)
_RE_CUSTOMER_PCT = re.compile(
    r"(?:one|a single|our largest|the largest)?\s*customer\s+"
    r"(?:accounted for|represented|comprised)\s+(?:approximately\s+)?(\d{1,2}(?:\.\d)?)\s?%\s+"
    r"of (?:our |the Company['’]?s |its |total |consolidated )*(?:net |total )*(?:revenue|sales)",
    re.I,
)


# ---------------- iXBRL 解析 ----------------

def _parse_contexts(soup: BeautifulSoup) -> dict[str, tuple[dict[str, str], Optional[str], Optional[str]]]:
    """context id → (维度{axis:member}, end_date, start_date)，全小写。"""
    out: dict[str, tuple[dict[str, str], Optional[str], Optional[str]]] = {}
    for c in soup.find_all(re.compile(r"context$", re.I)):
        cid = c.get("id")
        if not cid:
            continue
        dims = {
            (em.get("dimension", "") or "").lower(): (em.text or "").strip().lower()
            for em in c.find_all(re.compile(r"explicitmember$", re.I))
        }
        ed = c.find(re.compile(r"enddate$", re.I))
        st = c.find(re.compile(r"startdate$", re.I))
        inst = c.find(re.compile(r"instant$", re.I))
        end = ed.text.strip() if ed else (inst.text.strip() if inst else None)
        start = st.text.strip() if st else None
        out[cid] = (dims, end, start)
    return out


def _fact_value(f) -> Optional[float]:
    """解析 ix:nonFraction 数值（含 scale / sign）。"""
    raw = (f.text or "").replace(",", "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    scale = int(f.get("scale") or 0)
    val *= 10 ** scale
    if f.get("sign") == "-":
        val = -val
    return val


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _primary_period_end(contexts: dict) -> Optional[str]:
    """文档主报告期 = 所有 context 中最大的 end_date（ISO 串，字典序即时间序）。

    10-K 含多年比较期事实，必须锚定主报告期，避免把陈旧比较期当现值。
    """
    # 仅取区间(duration)context 的 end（财年末），排除封面 dei 等瞬时日期
    ends = [end for _, (_, end, start) in contexts.items() if end and start]
    return max(ends) if ends else None


def extract_customer_concentration(
    soup: BeautifulSoup, contexts: dict, plain_text: str
) -> tuple[Optional[float], Optional[date]]:
    """top1 客户占营收比（0-1）+ 对应财年末。iXBRL 优先、文本兜底。

    仅认**文档主报告期**的「客户口径」集中度事实，三重维度精确筛选（实测排除误报）：
      ① benchmark = RevenueFromContractWithCustomer（营收口径，排除应收）
      ② type = CustomerConcentrationRisk（排除地理/产品/渠道集中度）
      ③ 存在具体大客户成员 MajorCustomersAxis（排除无成员的 100% 合计行）
    取主报告期最大值即 top 客户(或披露客户群)占营收比；
    主报告期无此事实但文本明示「无客户 >10%」→ 视为分散不记信号。
    返回 (pct, period_end)；无任何信号返回 (None, None)。
    """
    primary = _primary_period_end(contexts)
    best_val: Optional[float] = None
    for f in soup.find_all("ix:nonfraction"):
        if "concentrationriskpercentage1" not in (f.get("name") or "").lower():
            continue
        dims, end, _ = contexts.get(f.get("contextref"), ({}, None, None))
        if dims.get(_AXIS_BENCHMARK) not in _MEMBERS_REVENUE:   # ① 营收口径
            continue
        if dims.get(_AXIS_RISK_TYPE) != _MEMBER_CUSTOMER_RISK:  # ② 客户类型
            continue
        member = dims.get(_AXIS_MAJOR_CUSTOMERS)
        if not member:                                          # ③ 具体大客户成员
            continue
        if _RE_AGGREGATE_CUSTOMER.search(member):               # ④ 排除合并客户群（仅留单一客户）
            continue
        if primary and end != primary:                          # 仅主报告期
            continue
        val = _fact_value(f)
        if val is None or not (0 < val <= 1.0):
            continue
        if best_val is None or val > best_val:
            best_val = val
    if best_val is not None:
        return best_val, _parse_date(primary)

    # 文本兜底
    if _RE_NO_CUSTOMER.search(plain_text):
        return None, None  # 明确披露无单一客户 >10% → 视为分散，不记信号
    pcts = [float(m) / 100.0 for m in _RE_CUSTOMER_PCT.findall(plain_text)]
    pcts = [p for p in pcts if 0 < p <= 1.0]
    if pcts:
        return max(pcts), _parse_date(primary)
    return None, None


def extract_segment_hhi(
    soup: BeautifulSoup, contexts: dict
) -> tuple[Optional[float], Optional[int], Optional[date]]:
    """最新财年分部营收 HHI（0-1，越高越集中）+ 分部数 + 财年末。

    仅取 `ConsolidationItems=OperatingSegments` × `BusinessSegments` 两轴的营收事实。
    返回 (hhi, n_segments, period_end)；不可计算返回 (None, None, None)。
    """
    # (start,end) → {segment_member: revenue}
    by_period: dict[tuple[Optional[str], Optional[str]], dict[str, float]] = {}
    for f in soup.find_all("ix:nonfraction"):
        if (f.get("name") or "").lower() not in _SEG_REVENUE_CONCEPTS:
            continue
        dims, end, start = contexts.get(f.get("contextref"), ({}, None, None))
        if _AXIS_SEG not in dims or dims.get(_AXIS_CONS) != _MEMBER_OPSEG:
            continue
        if len(dims) != 2:  # 仅 consolidation + segment 两轴（排除产品/地区细分）
            continue
        member = dims[_AXIS_SEG]
        if _SEG_MEMBER_EXCLUDE.search(member):
            continue
        val = _fact_value(f)
        if val is None:
            continue
        by_period.setdefault((start, end), {})[member] = val

    if not by_period:
        return None, None, None
    # 取 end 最新的一期
    (start, end), segs = max(by_period.items(), key=lambda kv: kv[0][1] or "")
    positives = {m: v for m, v in segs.items() if v > 0}
    if len(positives) < 2:  # 单一分部或不可比 → 不计（避免 HHI=1 噪声）
        return None, None, None
    total = sum(positives.values())
    if total <= 0:
        return None, None, None
    hhi = sum((v / total) ** 2 for v in positives.values())
    return hhi, len(positives), _parse_date(end)


def extract_supplier_flag(plain_text: str) -> Optional[str]:
    """供应商集中度定性旗标：命中返回匹配短语，否则 None。"""
    m = _SUPPLIER_PATTERNS.search(plain_text)
    return m.group(0) if m else None


def _plain_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))


# ---------------- 落库 ----------------

def _sig_id(company_id: str, stype: str, doc_id) -> str:
    return hashlib.sha256(f"{company_id}_{stype}_{doc_id}".encode()).hexdigest()[:64]


def _fiscal_year_end_fallback(db: Session, company_id: str, published_at) -> Optional[date]:
    """iXBRL 未给 period_end 时，按公司财年末月 + 披露日推断最近财年末。"""
    from backend.metrics.helpers import get_fiscal_year_end
    fy = get_fiscal_year_end(db, company_id)
    if fy is None or published_at is None:
        return None
    y = published_at.year
    # 10-K 通常在财年末后 1-3 月披露；取披露日之前最近的财年末月
    for cand_year in (y, y - 1):
        cand = date(cand_year, fy, 28)
        if cand <= published_at.date():
            return cand
    return None


def process_one_10k(
    db: Session, doc_id, company_id: str, content_url: str, published_at, *,
    existing_sigs: Optional[set] = None,
) -> dict:
    """抽取单份 10-K → 写 metric_periodic（客户/HHI）+ governance_signal（供应商）。"""
    from backend.metrics.compute import _upsert_metric

    html = sec_get_raw(content_url)
    if not html:
        return {"fetched": False}
    soup = BeautifulSoup(html, "lxml")
    contexts = _parse_contexts(soup)
    text = _plain_text(soup)

    cust_pct, cust_pe = extract_customer_concentration(soup, contexts, text)
    hhi, n_seg, seg_pe = extract_segment_hhi(soup, contexts)
    supplier = extract_supplier_flag(text)

    fallback_pe = _fiscal_year_end_fallback(db, company_id, published_at)
    out = {"fetched": True, "customer": None, "hhi": None, "supplier": bool(supplier)}

    if cust_pct is not None:
        pe = cust_pe or fallback_pe
        if pe:
            _upsert_metric(db, company_id, pe, "top_customer_revenue_pct", cust_pct,
                           [], "SEC-10K", formula_version=FORMULA_VERSION)
            out["customer"] = cust_pct
    if hhi is not None:
        pe = seg_pe or fallback_pe
        if pe:
            _upsert_metric(db, company_id, pe, "segment_revenue_hhi", hhi,
                           [], f"n_seg={n_seg}", formula_version=FORMULA_VERSION)
            _upsert_metric(db, company_id, pe, "segment_count", float(n_seg),
                           [], None, formula_version=FORMULA_VERSION)
            out["hhi"] = hhi
    if supplier:
        sid = _sig_id(company_id, "supplier_concentration", doc_id)
        if existing_sigs is None or sid not in existing_sigs:
            ev = published_at.date() if published_at else (fallback_pe or date.today())
            db.merge(GovernanceSignal(
                signal_id=sid, company_id=company_id,
                signal_type="supplier_concentration", severity="soft",
                event_date=ev, value=None,
                detail=f"供应商集中度（定性）：10-K 披露「{supplier[:80]}」",
                source_type="SEC-10K", source_doc_id=str(doc_id),
            ))
            if existing_sigs is not None:
                existing_sigs.add(sid)
    db.commit()
    return out


def backfill_commercial_signals(db: Session, *, limit: Optional[int] = None) -> dict:
    """扫全部 10-K text_document（含 content_url）→ 抽取商业信号入库（幂等）。"""
    rows = db.execute(
        select(TextDocument.doc_id, TextDocument.company_id,
               TextDocument.content_url, TextDocument.published_at)
        .where(TextDocument.doc_type == "10-K")
        .where(TextDocument.content_url.isnot(None))
        .order_by(TextDocument.company_id, TextDocument.published_at.desc())
    ).all()
    if limit:
        rows = rows[:limit]

    existing_sigs = set(db.execute(
        select(GovernanceSignal.signal_id)
        .where(GovernanceSignal.signal_type == "supplier_concentration")
    ).scalars())

    stat = {"total": len(rows), "fetched": 0, "customer": 0, "hhi": 0, "supplier": 0, "failed": 0}
    for i, (doc_id, cid, url, pub) in enumerate(rows, 1):
        try:
            r = process_one_10k(db, doc_id, cid, url, pub, existing_sigs=existing_sigs)
            if not r.get("fetched"):
                stat["failed"] += 1
                continue
            stat["fetched"] += 1
            if r.get("customer") is not None:
                stat["customer"] += 1
            if r.get("hhi") is not None:
                stat["hhi"] += 1
            if r.get("supplier"):
                stat["supplier"] += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            stat["failed"] += 1
            log.exception("commercial extract failed doc=%s cid=%s: %s", doc_id, cid, e)
        if i % 50 == 0:
            log.info("进度 %d/%d  %s", i, stat["total"], stat)
    return stat


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="美股 10-K 商业深度风险抽取")
    p.add_argument("--limit", type=int, default=None, help="仅处理前 N 份（调试）")
    args = p.parse_args()
    db = SessionLocal()
    try:
        res = backfill_commercial_signals(db, limit=args.limit)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    finally:
        db.close()
