# -*- coding: utf-8 -*-
"""A股数据管道运行器"""
from loguru import logger
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.pipeline.cn_stock.akshare_client import (
    ingest_cn_company_info,
    ingest_cn_financials,
    ingest_cn_market_data,
)

# 样本 A 股列表
SAMPLE_CN_STOCKS = {
    "600519": "贵州茅台",
    "000858": "五粮液",
    "601318": "中国平安",
    "600036": "招商银行",
    "000333": "美的集团",
    "600276": "恒瑞医药",
    "002415": "海康威视",
    "601012": "隆基绿能",
    "600900": "长江电力",
    "000651": "格力电器",
}


def ingest_cn_company(db: Session, stock_code: str, name: str) -> bool:
    """拉取单个 A 股公司的全部数据"""
    try:
        ingest_cn_company_info(db, stock_code, name)
        ingest_cn_financials(db, stock_code)
        ingest_cn_market_data(db, stock_code)
        return True
    except Exception as e:
        logger.error(f"A股 {stock_code} {name} 拉取失败: {e}")
        return False


def run_sample_ingestion():
    """拉取样本 A 股数据"""
    db = SessionLocal()
    try:
        success = 0
        for code, name in SAMPLE_CN_STOCKS.items():
            logger.info(f"开始拉取 {name} ({code})...")
            ok = ingest_cn_company(db, code, name)
            if ok:
                success += 1
        logger.info(f"A股样本拉取完成: {success}/{len(SAMPLE_CN_STOCKS)} 成功")
    finally:
        db.close()


if __name__ == "__main__":
    run_sample_ingestion()
