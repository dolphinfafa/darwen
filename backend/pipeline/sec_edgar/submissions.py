# -*- coding: utf-8 -*-
"""SEC EDGAR submissions：拉取公司元数据（CIK → ticker/行业/交易所）"""
import hashlib
from datetime import date

from loguru import logger
from sqlalchemy.orm import Session

from backend.models import Company, Security, Filing
from backend.pipeline.sec_edgar.rate_limiter import sec_get


def _make_company_id(cik: str) -> str:
    return f"US_{cik.zfill(10)}"


def _make_security_id(ticker: str, exchange: str) -> str:
    raw = f"{ticker}_{exchange}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def fetch_submission(cik: str) -> dict | None:
    """拉取单个公司的 submissions JSON"""
    padded_cik = f"CIK{cik.zfill(10)}"
    path = f"/submissions/{padded_cik}.json"
    return sec_get(path)


def parse_and_store_submission(db: Session, data: dict) -> Company | None:
    """解析 submissions JSON，存入 company/security/filing 表"""
    if not data:
        return None

    cik = str(data.get("cik", ""))
    company_id = _make_company_id(cik)
    name = data.get("name", "")
    sic = data.get("sic", "")
    sic_desc = data.get("sicDescription", "")
    tickers = data.get("tickers", [])
    exchanges = data.get("exchanges", [])

    # upsert company
    company = db.get(Company, company_id)
    if not company:
        company = Company(
            company_id=company_id,
            market="US",
            name=name,
            name_en=name,
            industry_code=sic,
            industry_name=sic_desc,
            currency="USD",
            cik=cik.zfill(10),
        )
        db.add(company)
    else:
        company.name = name
        company.industry_code = sic
        company.industry_name = sic_desc

    # upsert securities
    for i, ticker in enumerate(tickers):
        exchange = exchanges[i] if i < len(exchanges) else ""
        sec_id = _make_security_id(ticker, exchange)
        existing = db.get(Security, sec_id)
        if not existing:
            db.add(Security(
                security_id=sec_id,
                company_id=company_id,
                ticker=ticker,
                exchange=exchange,
            ))

    # parse recent filings
    recent = data.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    for j in range(min(len(accession_numbers), 200)):  # 最多存 200 条近期
        acc_no = accession_numbers[j]
        filing_id = f"SEC_{acc_no.replace('-', '')}"
        existing_filing = db.get(Filing, filing_id)
        if existing_filing:
            continue

        form_type = forms[j] if j < len(forms) else None
        filed = filing_dates[j] if j < len(filing_dates) else None
        doc = primary_docs[j] if j < len(primary_docs) else ""

        filed_date = None
        if filed:
            try:
                filed_date = date.fromisoformat(filed)
            except ValueError:
                pass

        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no.replace('-', '')}/{doc}"

        db.add(Filing(
            filing_id=filing_id,
            company_id=company_id,
            source_type="SEC",
            form_type=form_type,
            filed_date=filed_date,
            available_date=filed_date,
            url=url,
        ))

    db.commit()
    logger.info(f"已存储公司 {name} (CIK={cik})，{len(tickers)} 个 ticker，{min(len(accession_numbers), 200)} 条 filing")
    return company
