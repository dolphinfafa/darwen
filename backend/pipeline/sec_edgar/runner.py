# -*- coding: utf-8 -*-
"""SEC EDGAR 数据管道运行器：批量拉取公司元数据 + XBRL 财务事实"""
from loguru import logger
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.pipeline.sec_edgar.submissions import fetch_submission, parse_and_store_submission, _make_company_id
from backend.pipeline.sec_edgar.company_facts import fetch_company_facts, parse_and_store_facts


# 样本美股列表（CIK → 公司名）
SAMPLE_US_STOCKS = {
    "320193": "Apple Inc.",
    "789019": "Microsoft Corp.",
    "1652044": "Alphabet Inc.",
    "1018724": "Amazon.com Inc.",
    "1045810": "NVIDIA Corp.",
    "1326801": "Meta Platforms Inc.",
    "1318605": "Tesla Inc.",
    "1067983": "Berkshire Hathaway Inc.",
    "51143": "Johnson & Johnson",
    "66740": "3M Company",
    "21344": "Coca-Cola Co.",
    "78003": "Pfizer Inc.",
    "200406": "The Procter & Gamble Co.",
    "93410": "Chevron Corp.",
    "2488": "AMD",
}


def ingest_company(db: Session, cik: str) -> bool:
    """拉取单个公司的 submissions + companyfacts"""
    try:
        sub_data = fetch_submission(cik)
        if not sub_data:
            logger.warning(f"CIK {cik}: submissions 返回空")
            return False

        company = parse_and_store_submission(db, sub_data)
        if not company:
            return False

        facts_data = fetch_company_facts(cik)
        if facts_data:
            company_id = _make_company_id(cik)
            parse_and_store_facts(db, company_id, facts_data)

        return True

    except Exception as e:
        logger.error(f"CIK {cik} 拉取失败: {e}")
        return False


def run_sample_ingestion():
    """拉取样本美股数据"""
    db = SessionLocal()
    try:
        success = 0
        for cik, name in SAMPLE_US_STOCKS.items():
            logger.info(f"开始拉取 {name} (CIK={cik})...")
            ok = ingest_company(db, cik)
            if ok:
                success += 1
        logger.info(f"样本拉取完成: {success}/{len(SAMPLE_US_STOCKS)} 成功")
    finally:
        db.close()


if __name__ == "__main__":
    run_sample_ingestion()
