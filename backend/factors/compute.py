# -*- coding: utf-8 -*-
"""因子计算入口：对单个公司计算全部因子"""
import hashlib
from datetime import date

from loguru import logger
from sqlalchemy.orm import Session

# 导入所有因子模块以触发注册
import backend.factors.survival  # noqa: F401
import backend.factors.replication  # noqa: F401
import backend.factors.adaptation  # noqa: F401
import backend.factors.moat  # noqa: F401
import backend.factors.valuation  # noqa: F401

from backend.factors.registry import get_all_factors
from backend.models import FactorValue


def compute_all_factors(db: Session, company_id: str, asof: date) -> dict[str, dict]:
    """计算单个公司的全部因子，返回 {factor_code: result_dict}"""
    results = {}
    all_factors = get_all_factors()

    for code, (func, dimension, desc) in all_factors.items():
        try:
            result = func(db, company_id, asof)
            results[code] = result
        except Exception as e:
            logger.warning(f"因子 {code} 计算失败 ({company_id}): {e}")
            results[code] = {"raw": {}, "redline": None, "error": str(e)}

    return results


def compute_and_store_factors(db: Session, company_id: str, asof: date) -> int:
    """计算全部因子并存入 factor_value 表"""
    results = compute_all_factors(db, company_id, asof)
    all_factors = get_all_factors()

    stored = 0
    for code, result in results.items():
        raw = result.get("raw", {})
        # 取第一个非 None 的值作为主要 raw_value
        primary_value = None
        for v in raw.values():
            if v is not None:
                primary_value = v
                break

        fv_id = hashlib.md5(f"{company_id}_{code}_{asof}".encode()).hexdigest()

        existing = db.get(FactorValue, fv_id)
        if existing:
            existing.raw_value = float(primary_value) if primary_value is not None else None
            existing.lineage = str(raw)
        else:
            db.add(FactorValue(
                factor_value_id=fv_id,
                company_id=company_id,
                factor_code=code,
                asof_date=asof,
                raw_value=float(primary_value) if primary_value is not None else None,
                cleaned_value=None,
                score=None,  # 评分引擎阶段填充
                normalization_bucket=None,
                lineage=str(raw),
            ))
        stored += 1

    db.commit()
    logger.info(f"公司 {company_id} 存储 {stored} 个因子值 (asof={asof})")
    return stored
