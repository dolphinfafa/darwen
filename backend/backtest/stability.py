# -*- coding: utf-8 -*-
"""
评分稳定性分析（Stability Engine）
- Top 公司评分追踪
- 评分波动率
- 分层迁移矩阵
"""
import numpy as np
from datetime import date
from collections import defaultdict

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.models import Company, ScoreSnapshot


def analyze_stability(
    db: Session,
    model: str = "balanced",
    market: str = "US",
    min_years: int = 3,
) -> dict:
    """
    分析评分稳定性。

    Returns: {
        "top_companies": [{company_id, name, scores: [{date, total, tier}], volatility}],
        "tier_transitions": {from_tier: {to_tier: count}},
        "avg_score_volatility": float,
        "persistence_rate": float,  # Top 公司次年仍是 Top 的比例
    }
    """
    # 获取所有评分快照
    snapshots = db.execute(
        select(ScoreSnapshot, Company.name)
        .join(Company, Company.company_id == ScoreSnapshot.company_id)
        .where(and_(
            ScoreSnapshot.model_version == model,
            ScoreSnapshot.total.isnot(None),
            Company.market == market,
        ))
        .order_by(ScoreSnapshot.company_id, ScoreSnapshot.asof_date)
    ).all()

    # 按公司分组
    company_scores = defaultdict(list)  # company_id -> [(date, total, tier, name)]
    for ss, name in snapshots:
        company_scores[ss.company_id].append({
            "date": str(ss.asof_date),
            "total": round(ss.total, 2),
            "tier": ss.tier,
            "name": name,
        })

    # Top 公司追踪（至少出现过一次 Top）
    top_companies = []
    all_volatilities = []

    for cid, scores in company_scores.items():
        if len(scores) < min_years:
            continue

        totals = [s["total"] for s in scores]
        vol = float(np.std(totals)) if len(totals) > 1 else 0
        all_volatilities.append(vol)

        has_top = any(s["tier"] == "Top" for s in scores)
        if has_top:
            top_companies.append({
                "company_id": cid,
                "name": scores[0]["name"],
                "scores": scores,
                "volatility": round(vol, 2),
                "avg_score": round(float(np.mean(totals)), 2),
                "n_years": len(scores),
                "top_count": sum(1 for s in scores if s["tier"] == "Top"),
            })

    top_companies.sort(key=lambda x: x["top_count"], reverse=True)

    # 分层迁移矩阵
    transitions = defaultdict(lambda: defaultdict(int))
    persistence_top = {"stayed": 0, "left": 0}

    for cid, scores in company_scores.items():
        for i in range(len(scores) - 1):
            from_tier = scores[i]["tier"]
            to_tier = scores[i + 1]["tier"]
            if from_tier and to_tier:
                transitions[from_tier][to_tier] += 1
                if from_tier == "Top":
                    if to_tier == "Top":
                        persistence_top["stayed"] += 1
                    else:
                        persistence_top["left"] += 1

    total_top = persistence_top["stayed"] + persistence_top["left"]
    persistence_rate = persistence_top["stayed"] / total_top * 100 if total_top > 0 else 0

    return {
        "top_companies": top_companies[:30],  # 最多返回 30 家
        "tier_transitions": {k: dict(v) for k, v in transitions.items()},
        "avg_score_volatility": round(float(np.mean(all_volatilities)), 2) if all_volatilities else 0,
        "persistence_rate": round(persistence_rate, 1),
        "total_companies_tracked": len(company_scores),
    }
