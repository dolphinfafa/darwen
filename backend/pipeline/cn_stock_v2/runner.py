# -*- coding: utf-8 -*-
"""A股数据管道 V2 运行器（Tushare Pro）"""
from loguru import logger

from backend.database import SessionLocal
from backend.pipeline.cn_stock_v2.tushare_client import ingest_one_stock


# 与旧 cn_stock 保持一致的 10 家蓝筹样本
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


def run_sample(start_date: str = "20140101"):
    """运行样本 A 股全量入库"""
    db = SessionLocal()
    try:
        success = 0
        all_stats = []
        for code, name in SAMPLE_CN_STOCKS.items():
            logger.info(f"开始 {name} ({code}) 全量入库...")
            stats = ingest_one_stock(db, code, name, start_date=start_date)
            all_stats.append(stats)
            if stats.get("status") == "ok":
                success += 1
                logger.success(
                    f"{name}: facts={stats.get('income_facts',0)+stats.get('balance_facts',0)+stats.get('cashflow_facts',0)}, "
                    f"filings={stats.get('filings',0)}, bars={stats.get('bars',0)}, "
                    f"anns={stats.get('announcements',0)}"
                )
        logger.info(f"完成: {success}/{len(SAMPLE_CN_STOCKS)} 成功")
        return all_stats
    finally:
        db.close()


if __name__ == "__main__":
    run_sample()
