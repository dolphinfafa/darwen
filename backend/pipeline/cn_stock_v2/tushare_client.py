# -*- coding: utf-8 -*-
"""Tushare Pro API 封装：财报、行情、披露日期、公告"""
import hashlib
import os
from datetime import date, datetime
from typing import Optional

import pandas as pd
import tushare as ts
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Company, Security, Fact, Filing, MarketBar, TextDocument,
)
from backend.pipeline.cn_stock_v2.field_map import (
    INCOME_FIELD_MAP, BALANCESHEET_FIELD_MAP, CASHFLOW_FIELD_MAP,
    DAILY_BASIC_FIELD_MAP, market_to_exchange, to_ts_code, from_ts_code,
)


_pro_api = None


def get_pro():
    """单例返回 Tushare Pro API（优先读 backend.config，回退到环境变量）"""
    global _pro_api
    if _pro_api is None:
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            try:
                from backend.config import get_settings
                token = get_settings().tushare_token
            except Exception:
                pass
        if not token:
            raise RuntimeError("TUSHARE_TOKEN 未配置（请在 .env 中设置）")
        ts.set_token(token)
        _pro_api = ts.pro_api()
    return _pro_api


# ---------- 工具函数 ----------

def _make_company_id(stock_code: str) -> str:
    return f"CN_{stock_code}"


def _make_security_id(stock_code: str) -> str:
    return hashlib.md5(f"CN_{stock_code}".encode()).hexdigest()[:16]


def _make_fact_id(company_id: str, account_code: str, period_end: str) -> str:
    raw = f"{company_id}_{account_code}_{period_end}"
    return hashlib.md5(raw.encode()).hexdigest()


def _make_filing_id(stock_code: str, ann_date: str, form_type: str) -> str:
    raw = f"{stock_code}_{ann_date}_{form_type}"
    return hashlib.md5(raw.encode()).hexdigest()[:32]


def _parse_date(s) -> Optional[date]:
    if not s or pd.isna(s):
        return None
    try:
        s = str(s).strip()
        if len(s) == 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return date.fromisoformat(s[:10])
    except Exception:
        return None


# ---------- 公司基础信息 ----------

def ingest_company_info(db: Session, stock_code: str, name: str = None,
                        industry: str = None, list_date: date = None) -> Company:
    """从 stock_basic 写入公司主数据"""
    company_id = _make_company_id(stock_code)
    company = db.get(Company, company_id)

    pro = get_pro()
    if not name or not industry:
        ts_code = to_ts_code(stock_code)
        df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name,industry,list_date,market")
        if df is not None and not df.empty:
            row = df.iloc[0]
            name = name or row.get("name")
            industry = industry or row.get("industry")
            ld_str = row.get("list_date")
            if ld_str and not list_date:
                list_date = _parse_date(ld_str)

    if not company:
        company = Company(
            company_id=company_id,
            market="CN_A",
            name=name or stock_code,
            industry_code="",
            industry_name=industry or "",
            currency="CNY",
            stock_code=stock_code,
            instrument_type="COMMON",
            list_date=list_date,
        )
        db.add(company)
    else:
        if name:
            company.name = name
        if industry:
            company.industry_name = industry
        if list_date:
            company.list_date = list_date

    sec_id = _make_security_id(stock_code)
    if not db.get(Security, sec_id):
        db.add(Security(
            security_id=sec_id,
            company_id=company_id,
            ticker=stock_code,
            exchange=market_to_exchange(stock_code),
        ))

    db.commit()
    return company


# ---------- 财务报表 ----------

def _ingest_financial_table(db: Session, ts_code: str, stock_code: str, df: pd.DataFrame,
                            field_map: dict, statement_label: str) -> int:
    """通用：把一张三表 DataFrame 按 field_map 写入 fact 表"""
    if df is None or df.empty:
        return 0

    company_id = _make_company_id(stock_code)
    existing_ids = set(
        row[0] for row in db.execute(
            select(Fact.fact_id).where(Fact.company_id == company_id)
        ).fetchall()
    )

    batch = []
    for _, row in df.iterrows():
        period_end = _parse_date(row.get("end_date"))
        if not period_end:
            continue
        ann_date = _parse_date(row.get("ann_date"))
        f_ann_date = _parse_date(row.get("f_ann_date"))  # 实际披露日
        accepted = f_ann_date or ann_date

        for ts_field, canonical in field_map.items():
            val = row.get(ts_field)
            if val is None or pd.isna(val):
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue

            fact_id = _make_fact_id(company_id, canonical, str(period_end))
            if fact_id in existing_ids:
                continue
            existing_ids.add(fact_id)

            batch.append(Fact(
                fact_id=fact_id,
                company_id=company_id,
                account_code="cn-cas",
                concept=canonical,
                unit="CNY",
                period_end=period_end,
                fiscal_year=period_end.year,
                value=fval,
                available_date=accepted,
                accepted_date=accepted,
                source_type="TS-FS",
                source_id=f"{statement_label}_{ts_code}",
            ))

    if batch:
        db.add_all(batch)
        db.commit()
    return len(batch)


def ingest_income(db: Session, stock_code: str, start_date: str = "20140101") -> int:
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    try:
        df = pro.income(ts_code=ts_code, start_date=start_date)
    except Exception as e:
        logger.warning(f"income {ts_code} 失败: {e}")
        return 0
    return _ingest_financial_table(db, ts_code, stock_code, df, INCOME_FIELD_MAP, "income")


def ingest_balancesheet(db: Session, stock_code: str, start_date: str = "20140101") -> int:
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    try:
        df = pro.balancesheet(ts_code=ts_code, start_date=start_date)
    except Exception as e:
        logger.warning(f"balancesheet {ts_code} 失败: {e}")
        return 0
    return _ingest_financial_table(db, ts_code, stock_code, df, BALANCESHEET_FIELD_MAP, "balancesheet")


def ingest_cashflow(db: Session, stock_code: str, start_date: str = "20140101") -> int:
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    try:
        df = pro.cashflow(ts_code=ts_code, start_date=start_date)
    except Exception as e:
        logger.warning(f"cashflow {ts_code} 失败: {e}")
        return 0
    return _ingest_financial_table(db, ts_code, stock_code, df, CASHFLOW_FIELD_MAP, "cashflow")


# ---------- 披露日期 ----------

def ingest_disclosure_dates(db: Session, stock_code: str, start_date: str = "20140101") -> int:
    """拉取 disclosure_date（财报实际披露日 + 预约日），写入 filing 表"""
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    try:
        df = pro.disclosure_date(ts_code=ts_code, start_date=start_date)
    except Exception as e:
        logger.warning(f"disclosure_date {ts_code} 失败: {e}")
        return 0
    if df is None or df.empty:
        return 0

    company_id = _make_company_id(stock_code)
    batch = []
    existing = set(
        row[0] for row in db.execute(
            select(Filing.filing_id).where(Filing.company_id == company_id)
        ).fetchall()
    )

    for _, row in df.iterrows():
        end_date = _parse_date(row.get("end_date"))
        if not end_date:
            continue
        actual = _parse_date(row.get("actual_date"))
        modify = _parse_date(row.get("modify_date"))
        pre_date = _parse_date(row.get("pre_date"))

        # 报告类型：年报/半年报/季报
        if end_date.month == 12:
            form_type = "年报"
        elif end_date.month == 6:
            form_type = "半年报"
        elif end_date.month in (3, 9):
            form_type = "季报"
        else:
            form_type = "其他"

        filing_id = _make_filing_id(stock_code, str(end_date), form_type)
        if filing_id in existing:
            continue
        existing.add(filing_id)

        batch.append(Filing(
            filing_id=filing_id,
            company_id=company_id,
            source_type="TS-DISC",
            form_type=form_type,
            title=f"{form_type} {end_date.isoformat()}",
            filed_date=actual or modify or pre_date,
            actual_disclosure_date=actual,
            available_date=actual or modify or pre_date,
        ))

    if batch:
        db.add_all(batch)
        db.commit()
    return len(batch)


# ---------- 行情 ----------

def ingest_daily(db: Session, stock_code: str, start_date: str = "20140101",
                 end_date: str = None) -> int:
    """日线行情 + daily_basic（PE/PB/市值），写入 market_bar"""
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")

    try:
        df_daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.warning(f"daily {ts_code} 失败: {e}")
        return 0
    try:
        df_basic = pro.daily_basic(
            ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields="ts_code,trade_date,close,pe_ttm,pb,total_mv,circ_mv,total_share",
        )
    except Exception:
        df_basic = pd.DataFrame()

    if df_daily is None or df_daily.empty:
        return 0

    df = df_daily
    if df_basic is not None and not df_basic.empty:
        df = df_daily.merge(
            df_basic[["trade_date", "pe_ttm", "pb", "total_mv", "total_share"]],
            on="trade_date", how="left",
        )

    security_id = _make_security_id(stock_code)
    existing_dates = set(
        row[0] for row in db.execute(
            select(MarketBar.trade_date).where(MarketBar.security_id == security_id)
        ).fetchall()
    )

    batch = []
    for _, row in df.iterrows():
        td = _parse_date(row.get("trade_date"))
        if not td or td in existing_dates:
            continue
        existing_dates.add(td)
        # market_cap 单位：Tushare daily_basic 的 total_mv 是万元
        mv_wan = row.get("total_mv") if "total_mv" in df.columns else None
        market_cap = float(mv_wan) * 10000 if mv_wan and not pd.isna(mv_wan) else None

        batch.append(MarketBar(
            security_id=security_id,
            trade_date=td,
            open=float(row.get("open", 0) or 0),
            high=float(row.get("high", 0) or 0),
            low=float(row.get("low", 0) or 0),
            close=float(row.get("close", 0) or 0),
            volume=float(row.get("vol", 0) or 0) * 100,  # tushare vol 单位：手 → 股
            market_cap=market_cap,
        ))

    if batch:
        db.add_all(batch)
        db.commit()
    return len(batch)


# ---------- 公告 ----------

def ingest_announcements(db: Session, stock_code: str, start_date: str = None) -> int:
    """拉取公司公告写入 text_document（doc_type=annual/interim/regulatory/other）

    需要 anns_d 接口权限；如无权限则静默跳过（A 股公告原文暂不入库，
    不影响主流程，AI 风险层会从巨潮备源补充）。
    """
    pro = get_pro()
    ts_code = to_ts_code(stock_code)
    company_id = _make_company_id(stock_code)

    if not start_date:
        start_date = (datetime.now().replace(year=datetime.now().year - 1)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")

    try:
        df = pro.anns_d(
            ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields="ts_code,name,ann_date,title,url",
        )
    except Exception as e:
        if "权限" in str(e) or "permission" in str(e).lower():
            logger.debug(f"anns_d {ts_code} 无权限，跳过公告原文入库")
            return 0
        logger.warning(f"anns_d {ts_code} 失败: {e}")
        return 0

    if df is None or df.empty:
        return 0

    # 用 (company_id, content_url) 去重
    existing_urls = set(
        row[0] for row in db.execute(
            select(TextDocument.content_url).where(
                TextDocument.company_id == company_id,
                TextDocument.source_type == "TS-ANN",
            )
        ).fetchall()
    )

    batch = []
    for _, row in df.iterrows():
        url = row.get("url")
        if not url or url in existing_urls:
            continue
        existing_urls.add(url)
        title = (row.get("title") or "").strip()
        ann_date = _parse_date(row.get("ann_date"))
        published_at = datetime.combine(ann_date, datetime.min.time()) if ann_date else None

        # 分类 doc_type
        if "年度报告" in title or "年报" in title:
            doc_type = "annual"
        elif "半年度" in title or "三季报" in title or "一季报" in title:
            doc_type = "interim"
        elif any(k in title for k in ["监管", "处罚", "立案", "问询", "警示"]):
            doc_type = "regulatory"
        else:
            doc_type = "other"

        sha = hashlib.sha256(url.encode()).hexdigest()
        batch.append(TextDocument(
            company_id=company_id,
            source_type="TS-ANN",
            doc_type=doc_type,
            title=title[:500],
            content_text=None,  # 仅存元数据，正文按需 lazy 拉
            content_url=url,
            content_sha256=sha,
            published_at=published_at,
        ))

    if batch:
        db.add_all(batch)
        db.commit()
    return len(batch)


# ---------- 编排：单股全量入库 ----------

def ingest_one_stock(db: Session, stock_code: str, name: str = None,
                     start_date: str = "20140101") -> dict:
    """单股全量入库：基础信息 + 三表 + 披露日期 + 行情 + 近期公告"""
    stats = {"stock_code": stock_code}
    try:
        ingest_company_info(db, stock_code, name)
        stats["income_facts"] = ingest_income(db, stock_code, start_date)
        stats["balance_facts"] = ingest_balancesheet(db, stock_code, start_date)
        stats["cashflow_facts"] = ingest_cashflow(db, stock_code, start_date)
        stats["filings"] = ingest_disclosure_dates(db, stock_code, start_date)
        stats["bars"] = ingest_daily(db, stock_code, start_date)
        stats["announcements"] = ingest_announcements(db, stock_code)
        stats["status"] = "ok"
    except Exception as e:
        logger.error(f"{stock_code} 全量入库失败: {e}")
        stats["status"] = "failed"
        stats["error"] = str(e)
    return stats
