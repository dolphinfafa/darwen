# -*- coding: utf-8 -*-
"""A股数据管道：通过 akshare 拉取财务报表和行情数据"""
import hashlib
from datetime import date

import pandas as pd
import akshare as ak
from loguru import logger
from sqlalchemy.orm import Session

from backend.models import Company, Security, Fact, MarketBar


def _make_company_id(stock_code: str) -> str:
    return f"CN_{stock_code}"


def _make_security_id(stock_code: str) -> str:
    return hashlib.md5(f"CN_{stock_code}".encode()).hexdigest()[:16]


def _make_fact_id(company_id: str, concept: str, period_end: str) -> str:
    raw = f"{company_id}_{concept}_{period_end}"
    return hashlib.md5(raw.encode()).hexdigest()


def _parse_cn_value(val) -> float | None:
    """解析中文数值：如 '893.35亿' → 89335000000.0, '1447.46万' → 14474600.0"""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s in ("", "False", "nan", "--", "-"):
        return None
    try:
        if s.endswith("亿"):
            return float(s[:-1]) * 1e8
        elif s.endswith("万"):
            return float(s[:-1]) * 1e4
        else:
            return float(s)
    except (ValueError, TypeError):
        return None


def _detect_exchange(stock_code: str) -> str:
    if stock_code.startswith("6"):
        return "SSE"
    elif stock_code.startswith(("0", "3")):
        return "SZSE"
    elif stock_code.startswith(("8", "4")):
        return "BSE"
    return "UNKNOWN"


def ingest_cn_company_info(db: Session, stock_code: str, name: str, industry: str = "") -> Company:
    """创建/更新 A 股公司基本信息"""
    company_id = _make_company_id(stock_code)
    company = db.get(Company, company_id)
    if not company:
        company = Company(
            company_id=company_id,
            market="CN_A",
            name=name,
            industry_code="",
            industry_name=industry,
            currency="CNY",
            stock_code=stock_code,
        )
        db.add(company)
    else:
        company.name = name
        if industry:
            company.industry_name = industry

    # security
    sec_id = _make_security_id(stock_code)
    existing_sec = db.get(Security, sec_id)
    if not existing_sec:
        db.add(Security(
            security_id=sec_id,
            company_id=company_id,
            ticker=stock_code,
            exchange=_detect_exchange(stock_code),
        ))

    db.commit()
    return company


def ingest_cn_financials(db: Session, stock_code: str) -> int:
    """通过 akshare 拉取 A 股利润表/资产负债表/现金流量表"""
    company_id = _make_company_id(stock_code)

    # 先查已有 fact_id
    from sqlalchemy import select
    existing_ids = set(
        row[0] for row in db.execute(
            select(Fact.fact_id).where(Fact.company_id == company_id)
        ).fetchall()
    )

    batch = []
    batch_ids = set()

    # 定义需要抓取的报表和字段映射
    report_configs = [
        {
            "func": lambda: ak.stock_financial_benefit_ths(symbol=stock_code, indicator="报告期"),
            "mappings": {
                "一、营业总收入": "revenue",
                "其中：营业收入": "revenue_operating",
                "五、净利润": "net_income",
                "归属于母公司所有者的净利润": "net_income_to_parent",
                "三、营业利润": "operating_income",
                "二、营业总成本": "total_cost",
                "研发费用": "rd_expense",
                "销售费用": "selling_expense",
                "管理费用": "admin_expense",
                "财务费用": "finance_expense",
                "其中：利息费用": "interest_expense",
            },
        },
        {
            "func": lambda: ak.stock_financial_debt_ths(symbol=stock_code, indicator="报告期"),
            "mappings": {
                "资产合计": "total_assets",
                "负债合计": "total_liabilities",
                "所有者权益（或股东权益）合计": "stockholders_equity",
                "归属于母公司所有者权益合计": "equity_to_parent",
                "流动资产合计": "current_assets",
                "流动负债合计": "current_liabilities",
                "货币资金": "cash",
                "短期借款": "short_term_debt",
                "长期借款": "long_term_debt",
                "固定资产合计": "ppe_net",
                "商誉": "goodwill",
                "无形资产": "intangible_assets",
                "实收资本（或股本）": "shares_outstanding_capital",
                "存货": "inventory",
            },
        },
        {
            "func": lambda: ak.stock_financial_cash_ths(symbol=stock_code, indicator="报告期"),
            "mappings": {
                "经营活动产生的现金流量净额": "ocf",
                "购建固定资产、无形资产和其他长期资产支付的现金": "capex_cash",
                "分配股利、利润或偿付利息支付的现金": "dividends_and_interest_paid",
                "取得借款收到的现金": "borrowings_received",
            },
        },
    ]

    for config in report_configs:
        try:
            df = config["func"]()
            if df is None or df.empty:
                continue
        except Exception as e:
            logger.warning(f"{stock_code} 报表拉取失败: {e}")
            continue

        # 查找日期列
        date_col = None
        for col in df.columns:
            if "报告期" in str(col) or "日期" in str(col):
                date_col = col
                break
        if date_col is None and len(df.columns) > 0:
            date_col = df.columns[0]

        for _, row in df.iterrows():
            period_str = str(row.get(date_col, ""))
            if not period_str or period_str == "nan":
                continue

            try:
                if len(period_str) == 4:
                    period_end = date(int(period_str), 12, 31)
                else:
                    period_end = date.fromisoformat(period_str[:10])
            except (ValueError, IndexError):
                continue

            for cn_name, canonical in config["mappings"].items():
                val = row.get(cn_name)
                float_val = _parse_cn_value(val)
                if float_val is None:
                    continue

                fact_id = _make_fact_id(company_id, canonical, str(period_end))
                if fact_id in existing_ids or fact_id in batch_ids:
                    continue

                batch_ids.add(fact_id)
                batch.append(Fact(
                    fact_id=fact_id,
                    company_id=company_id,
                    taxonomy_or_account="cn-cas",
                    concept=canonical,
                    unit="CNY",
                    period_end=period_end,
                    value=float_val,
                    available_date=None,
                    source_type="AKSHARE",
                    source_id=f"ths_{stock_code}",
                ))

    if batch:
        db.add_all(batch)
        db.commit()

    logger.info(f"A股 {stock_code} 存储 {len(batch)} 条财务 facts")
    return len(batch)


def ingest_cn_market_data(db: Session, stock_code: str, start_date: str = "20200101") -> int:
    """拉取 A 股日线行情数据"""
    security_id = _make_security_id(stock_code)

    try:
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_date, adjust="qfq")
        if df is None or df.empty:
            return 0
    except Exception as e:
        logger.warning(f"{stock_code} 行情拉取失败: {e}")
        return 0

    # 查已有日期
    from sqlalchemy import select
    existing_dates = set(
        row[0] for row in db.execute(
            select(MarketBar.trade_date).where(MarketBar.security_id == security_id)
        ).fetchall()
    )

    batch = []
    for _, row in df.iterrows():
        try:
            trade_date = pd.Timestamp(row["日期"]).date()
        except Exception:
            continue

        if trade_date in existing_dates:
            continue

        batch.append(MarketBar(
            security_id=security_id,
            trade_date=trade_date,
            open=float(row.get("开盘", 0)),
            high=float(row.get("最高", 0)),
            low=float(row.get("最低", 0)),
            close=float(row.get("收盘", 0)),
            volume=float(row.get("成交量", 0)),
            market_cap=None,
        ))

    if batch:
        db.add_all(batch)
        db.commit()

    logger.info(f"A股 {stock_code} 存储 {len(batch)} 条日线行情")
    return len(batch)
