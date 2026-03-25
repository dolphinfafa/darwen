# -*- coding: utf-8 -*-
"""评分引擎：加权聚合 + 红线 gating + Top/Watch/Reject 分层"""
import hashlib
import json
from datetime import date

import numpy as np

from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from backend.models import FactorValue, ScoreSnapshot, Company
from backend.factors.registry import get_all_factors, ALL_DIMENSIONS
from backend.factors.normalizer import percentile_normalize
from backend.scoring.weights import DIMENSION_WEIGHTS, FACTOR_WEIGHTS, TIER_THRESHOLDS


# 因子方向：值越大越好 = "higher_better"，越大越差 = "lower_better"
FACTOR_DIRECTION = {
    # 生存力
    "S1": "lower_better",   # net_debt/ebitda 越低越好
    "S2": "higher_better",  # 流动比率越高越好
    "S3": "higher_better",  # FCF margin 越高越好
    "S4": "higher_better",  # OCF/NI 越高越好
    "S5": "lower_better",   # 稀释越低越好
    "S6": "lower_better",   # 风险事件越少越好
    # 复制力
    "R1": "higher_better",  # ROIC 越高越好
    "R2": "higher_better",  # 增量 ROIC
    "R3": "higher_better",  # 收入 CAGR
    "R4": "higher_better",  # 毛利率
    "R5": "higher_better",  # 再投资率（适中最好，但简化为 higher）
    "R6": "higher_better",
    # 适应力
    "A1": "higher_better",  # 跌幅越小（值越大）越好
    "A2": "lower_better",   # 毛利波动越低越好
    "A3": "higher_better",  # 研发效率
    "A4": "lower_better",   # 集中度风险越低越好
    "A5": "higher_better",  # 治理分越高越好
    "A6": "lower_better",   # 监管事件占比越低越好
    # 优势积累
    "M1": "higher_better",  # 定价权
    "M2": "higher_better",  # 复利
    "M3": "higher_better",  # 市占率代理
    "M4": "higher_better",  # SGA 杠杆
    "M5": "higher_better",  # 反脆弱分
    "M6": "higher_better",  # 叙事一致性
    # 估值
    "V1": "higher_better",  # 估值相关（评分后越高越好）
    "V2": "higher_better",  # 安全边际越大越好
    "V3": "higher_better",  # 增长越高越好
    "V4": "lower_better",   # 回撤买点：回撤越深（负值越小）= 估值越有吸引力
    "V5": "higher_better",  # 估值安全度（Earnings Yield 越高越便宜）
    "V6": "higher_better",  # 流动性越好越好
}


def _collect_universe_values(db: Session, factor_code: str, asof: date, market: str | None = None) -> list[float]:
    """收集某因子在全市场的原始值分布（用于归一化）"""
    stmt = (
        select(FactorValue.raw_value)
        .where(and_(
            FactorValue.factor_code == factor_code,
            FactorValue.asof_date == asof,
            FactorValue.raw_value.isnot(None),
        ))
    )

    if market:
        stmt = stmt.join(Company, Company.company_id == FactorValue.company_id)
        stmt = stmt.where(Company.market == market)

    return [row[0] for row in db.execute(stmt).fetchall()]


def normalize_factors(db: Session, company_id: str, asof: date, market: str | None = None) -> dict[str, float]:
    """对单个公司的全部因子做分位数归一化，返回 {factor_code: score_0_100}"""
    # 获取该公司的全部因子值
    stmt = select(FactorValue).where(and_(
        FactorValue.company_id == company_id,
        FactorValue.asof_date == asof,
    ))
    factor_rows = {fv.factor_code: fv for fv in db.execute(stmt).scalars().all()}

    scores = {}
    for code, fv in factor_rows.items():
        if fv.raw_value is None:
            # stub/无数据因子 → 不参与评分（scores 中不设值）
            fv.score = None
            continue

        universe = _collect_universe_values(db, code, asof, market)
        direction = FACTOR_DIRECTION.get(code, "higher_better")

        if direction == "lower_better":
            # 反转：原始值越低分越高
            score = percentile_normalize(fv.raw_value, universe)
            if score is not None:
                score = 100.0 - score
        else:
            score = percentile_normalize(fv.raw_value, universe)

        if score is None:
            score = 50.0

        scores[code] = score
        fv.score = score

    db.commit()
    return scores


def compute_dimension_scores(
    factor_scores: dict[str, float],
    factor_redlines: dict[str, str | None],
) -> tuple[dict[str, float], list[str]]:
    """
    计算五个维度得分 + 收集红线。
    NA 因子的权重等比例重分配给有值因子。
    """
    dim_scores = {}
    all_redlines = []

    for dim in ALL_DIMENSIONS:
        weights = FACTOR_WEIGHTS.get(dim, {})
        weighted_sum = 0.0
        total_weight = 0.0

        for code, w in weights.items():
            score = factor_scores.get(code)  # None = stub/无数据，不参与
            if score is not None:
                weighted_sum += w * score
                total_weight += w

            redline = factor_redlines.get(code)
            if redline:
                all_redlines.append(f"{code}:{redline}")

        if total_weight > 0:
            dim_scores[dim] = weighted_sum / total_weight
        else:
            dim_scores[dim] = 50.0  # 全部缺失给中性分

    return dim_scores, all_redlines


def compute_total_score(
    dim_scores: dict[str, float],
    model: str = "balanced",
) -> float:
    """计算总分 = 五维度加权聚合"""
    weights = DIMENSION_WEIGHTS.get(model, DIMENSION_WEIGHTS["balanced"])
    total = sum(weights[dim] * dim_scores.get(dim, 50.0) for dim in ALL_DIMENSIONS)
    return total


def classify_tier(total_score: float, redlines: list[str], top_threshold: float = 65.0, watch_threshold: float = 45.0) -> str:
    """分层：Top/Watch/Reject"""
    strong_redlines = {"interest_coverage_below_1.5", "high_dilution_above_30pct"}
    for rl in redlines:
        tag = rl.split(":")[-1] if ":" in rl else rl
        if tag in strong_redlines:
            return "Reject"

    if total_score >= top_threshold and not redlines:
        return "Top"
    elif total_score >= watch_threshold:
        return "Watch"
    else:
        return "Reject"


def batch_classify_tiers(db: Session, asof: date, model: str = "balanced"):
    """批量分层：用分位数动态确定阈值"""
    from backend.scoring.weights import TIER_PERCENTILES

    snapshots = db.query(ScoreSnapshot).filter(and_(
        ScoreSnapshot.asof_date == asof,
        ScoreSnapshot.model_version == model,
    )).all()

    if not snapshots:
        return

    scores = [s.total for s in snapshots if s.total is not None]
    if not scores:
        return

    top_threshold = float(np.percentile(scores, TIER_PERCENTILES["Top"]))
    watch_threshold = float(np.percentile(scores, TIER_PERCENTILES["Watch"]))

    for s in snapshots:
        redlines = json.loads(s.gating_flags) if s.gating_flags else []
        s.tier = classify_tier(s.total or 0, redlines, top_threshold, watch_threshold)

    db.commit()
    return {"top_threshold": top_threshold, "watch_threshold": watch_threshold}


def score_company(
    db: Session,
    company_id: str,
    asof: date,
    model: str = "balanced",
    market: str | None = None,
) -> ScoreSnapshot:
    """完整评分流程：归一化 → 维度得分 → 总分 → 分层"""
    # 1. 归一化
    factor_scores = normalize_factors(db, company_id, asof, market)

    # 2. 收集红线（从 factor_value.lineage 解析）
    factor_redlines = {}
    from backend.factors.compute import compute_all_factors
    raw_results = compute_all_factors(db, company_id, asof)
    for code, result in raw_results.items():
        factor_redlines[code] = result.get("redline")

    # 3. 维度得分
    dim_scores, redlines = compute_dimension_scores(factor_scores, factor_redlines)

    # 4. 总分
    total = compute_total_score(dim_scores, model)

    # 5. 分层
    tier = classify_tier(total, redlines)

    # 6. 存储
    score_id = hashlib.md5(f"{company_id}_{asof}_{model}".encode()).hexdigest()
    existing = db.get(ScoreSnapshot, score_id)
    if existing:
        snapshot = existing
    else:
        snapshot = ScoreSnapshot(score_id=score_id)
        db.add(snapshot)

    snapshot.company_id = company_id
    snapshot.asof_date = asof
    snapshot.model_version = model
    snapshot.survival = dim_scores.get("survival")
    snapshot.replication = dim_scores.get("replication")
    snapshot.adaptation = dim_scores.get("adaptation")
    snapshot.moat = dim_scores.get("moat")
    snapshot.valuation = dim_scores.get("valuation")
    snapshot.total = total
    snapshot.tier = tier
    snapshot.gating_flags = json.dumps(redlines) if redlines else None

    db.commit()
    logger.info(f"评分 {company_id} [{model}]: total={total:.1f}, tier={tier}, dims={dim_scores}")
    return snapshot
