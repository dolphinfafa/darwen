# -*- coding: utf-8 -*-
"""SEC EDGAR XBRL companyfacts：拉取财务事实（revenue, net_income, ocf, capex 等）"""
import hashlib
from datetime import date

from loguru import logger
from sqlalchemy.orm import Session

from backend.models import Fact
from backend.pipeline.sec_edgar.rate_limiter import sec_get

# 需要抓取的核心 XBRL concepts（us-gaap taxonomy）
CORE_CONCEPTS = [
    # 收入与利润
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "GrossProfit",
    "OperatingIncomeLoss",
    # 资产负债
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "LongTermDebtCurrent",
    "ShortTermBorrowings",
    "CommercialPaper",
    "CashAndCashEquivalentsAtCarryingValue",
    "ShortTermInvestments",
    "MarketableSecuritiesCurrent",
    "CurrentAssets",
    "AssetsCurrent",
    "CurrentLiabilities",
    "LiabilitiesCurrent",
    "OperatingLeaseLiabilityCurrent",
    "FinanceLeaseLiabilityCurrent",
    # 现金流
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsOfDividends",
    "PaymentsForRepurchaseOfCommonStock",
    # 股本
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    # 费用
    "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense",
    "InterestExpense",
    # EBITDA 相关
    "DepreciationAndAmortization",
    "DepreciationDepletionAndAmortization",
    # 投入资本
    "PropertyPlantAndEquipmentNet",
    "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill",
]


# dei taxonomy 的实体级元数据（与 us-gaap 平级）
# 金融股的真实流通股本在 dei.EntityCommonStockSharesOutstanding，
# us-gaap.CommonStockSharesOutstanding 对它们多数只有 2008-2009 历史值
DEI_CONCEPTS = [
    "EntityCommonStockSharesOutstanding",
]


def _make_fact_id(company_id: str, concept: str, period_end: str, unit: str, form: str, filed: str) -> str:
    raw = f"{company_id}_{concept}_{period_end}_{unit}_{form}_{filed}"
    return hashlib.md5(raw.encode()).hexdigest()


def fetch_company_facts(cik: str) -> dict | None:
    """拉取单个公司的全部 XBRL facts"""
    padded_cik = f"CIK{cik.zfill(10)}"
    path = f"/api/xbrl/companyfacts/{padded_cik}.json"
    return sec_get(path)


def parse_and_store_facts(db: Session, company_id: str, data: dict) -> int:
    """解析 companyfacts JSON，筛选核心 concepts 并批量存入 fact 表。

    遍历 us-gaap + dei 两个 taxonomy。account_code 字段记录 taxonomy 名
    便于后续 field_map 区分（dei 字段为实体级元数据，如真实流通股本）。
    """
    if not data:
        return 0

    facts_section = data.get("facts", {})

    # 先查询已有 fact_id 集合，避免逐条查库
    from sqlalchemy import select
    existing_ids = set(
        row[0] for row in db.execute(
            select(Fact.fact_id).where(Fact.company_id == company_id)
        ).fetchall()
    )

    batch = []
    batch_ids = set()

    # (taxonomy_name, concept_list) 双轨遍历
    for taxonomy, concepts in (("us-gaap", CORE_CONCEPTS), ("dei", DEI_CONCEPTS)):
        tx_data = facts_section.get(taxonomy, {})
        for concept_name in concepts:
            concept_data = tx_data.get(concept_name)
            if not concept_data:
                continue

            units = concept_data.get("units", {})
            for unit_type, entries in units.items():
                for entry in entries:
                    form = entry.get("form", "")
                    if form not in ("10-K", "10-Q"):
                        continue

                    period_end = entry.get("end")
                    if not period_end:
                        continue

                    val = entry.get("val")
                    filed = entry.get("filed", "")

                    fact_id = _make_fact_id(company_id, concept_name, period_end, unit_type, form, filed)

                    if fact_id in existing_ids or fact_id in batch_ids:
                        continue

                    filed_date = None
                    if filed:
                        try:
                            filed_date = date.fromisoformat(filed)
                        except ValueError:
                            pass

                    try:
                        period_end_date = date.fromisoformat(period_end)
                    except ValueError:
                        continue

                    batch_ids.add(fact_id)
                    batch.append(Fact(
                        fact_id=fact_id,
                        company_id=company_id,
                        account_code=taxonomy,
                        concept=concept_name,
                        unit=unit_type,
                        period_end=period_end_date,
                        fiscal_year=period_end_date.year,
                        value=float(val) if val is not None else None,
                        available_date=filed_date,
                        accepted_date=filed_date,
                        source_type="SEC",
                        source_id=f"companyfacts_{company_id}",
                    ))

    # 批量写入
    if batch:
        db.add_all(batch)
        db.commit()
    logger.info(f"公司 {company_id} 存储 {len(batch)} 条 XBRL facts")
    return len(batch)
