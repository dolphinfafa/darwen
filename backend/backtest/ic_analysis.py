# -*- coding: utf-8 -*-
"""
因子有效性分析（Factor IC Engine）
- IC = Rank Correlation(因子值, 未来收益)
- ICIR = IC均值 / IC标准差
"""
import numpy as np
from datetime import date, timedelta
from collections import defaultdict

from loguru import logger
from scipy import stats
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.models import Company, Security, FactorValue, MarketBar
from backend.backtest.engine_v2 import get_security_id, get_price_near


def compute_factor_ic(
    db: Session,
    start_year: int = 2013,
    end_year: int = 2024,
    market: str = "US",
    forward_months: int = 12,
) -> dict:
    """
    计算每个因子在每个时间点的 IC（Spearman Rank Correlation）。

    Returns: {
        "factors": {
            "S1": {ic_mean, ic_std, icir, positive_ratio, ic_series: [{date, ic}]},
            ...
        },
        "ranking": [{factor, ic_mean, icir, verdict}],
    }
    """
    # 收集所有 asof_date
    asof_dates = []
    for y in range(start_year, end_year):
        asof_dates.append(date(y, 12, 31))

    # factor_code -> [(date, ic_value)]
    factor_ics = defaultdict(list)

    for asof in asof_dates:
        forward_date = date(asof.year + 1, 12, 31) if forward_months == 12 else asof + timedelta(days=forward_months * 30)

        # 取该期所有因子值
        fv_rows = db.execute(
            select(FactorValue)
            .join(Company, Company.company_id == FactorValue.company_id)
            .where(and_(
                FactorValue.asof_date == asof,
                FactorValue.raw_value.isnot(None),
                Company.market == market,
            ))
        ).scalars().all()

        # 按 factor_code 分组
        factor_groups = defaultdict(list)  # code -> [(company_id, raw_value)]
        for fv in fv_rows:
            factor_groups[fv.factor_code].append((fv.company_id, fv.raw_value))

        # 计算每只股票的前向收益
        forward_returns = {}
        company_ids = set(fv.company_id for fv in fv_rows)
        for cid in company_ids:
            sec_id = get_security_id(db, cid)
            if not sec_id:
                continue
            bp = get_price_near(db, sec_id, asof)
            sp = get_price_near(db, sec_id, forward_date)
            if bp and sp and bp > 0:
                ret = (sp / bp) - 1
                ret = max(min(ret, 5.0), -0.9)
                forward_returns[cid] = ret

        # 对每个因子计算 IC
        for code, pairs in factor_groups.items():
            factor_vals = []
            return_vals = []
            for cid, raw in pairs:
                if cid in forward_returns:
                    factor_vals.append(raw)
                    return_vals.append(forward_returns[cid])

            if len(factor_vals) < 10:
                continue

            # Spearman Rank IC
            ic, _ = stats.spearmanr(factor_vals, return_vals)
            if not np.isnan(ic):
                factor_ics[code].append((str(asof), round(float(ic), 4)))

    # 汇总
    factors = {}
    for code, ic_series in factor_ics.items():
        ic_values = [v for _, v in ic_series]
        arr = np.array(ic_values)
        ic_mean = float(np.mean(arr))
        ic_std = float(np.std(arr)) if len(arr) > 1 else 0
        icir = ic_mean / ic_std if ic_std > 0 else 0
        pos_ratio = float(np.mean(arr > 0))

        factors[code] = {
            "ic_mean": round(ic_mean, 4),
            "ic_std": round(ic_std, 4),
            "icir": round(icir, 2),
            "positive_ratio": round(pos_ratio * 100, 1),
            "n_periods": len(ic_series),
            "ic_series": [{"date": d, "ic": v} for d, v in ic_series],
        }

    # 排名
    ranking = sorted(
        [
            {
                "factor": code,
                "ic_mean": info["ic_mean"],
                "icir": info["icir"],
                "positive_ratio": info["positive_ratio"],
                "verdict": _verdict(info["ic_mean"], info["icir"]),
            }
            for code, info in factors.items()
        ],
        key=lambda x: abs(x["ic_mean"]),
        reverse=True,
    )

    return {"factors": factors, "ranking": ranking}


def _verdict(ic_mean: float, icir: float) -> str:
    abs_ic = abs(ic_mean)
    if abs_ic >= 0.05 and abs(icir) >= 0.5:
        return "STRONG"
    if abs_ic >= 0.03:
        return "MODERATE"
    if abs_ic >= 0.01:
        return "WEAK"
    return "INEFFECTIVE"
