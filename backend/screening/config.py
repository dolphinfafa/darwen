# -*- coding: utf-8 -*-
"""三层漏斗筛选配置（阈值默认值 + 三档严格度）。

config 通过 funnel.run() 透传，前端 ScreenConfig 表单可覆盖任意字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScreenConfig:
    """筛选配置。"""
    # Q 层
    roce_threshold: float = 0.20        # Q3 门槛
    roce_count_required_5y: int = 4     # 5 年中 ≥ threshold 的年数
    roce_count_required_10y: int = 8    # 10 年中 ≥ threshold 的年数（Q4 强通过）
    min_list_years: int = 5             # Q6 上市年限
    min_fiscal_years: int = 5           # Q1 财年数

    # R 层敏感度（strict / standard / loose）— 阈值随之调整
    risk_sensitivity: str = "standard"

    # V 层估值模式
    valuation_mode: str = "strict"  # strict / standard / loose

    # AI provider（M3 暂未消费，留给 M4）
    ai_provider: str | None = None

    # M3 阶段：R 层是否启用 AI（默认 False，全部走 RULE_ONLY）
    enable_ai_risk_layer: bool = False

    @property
    def r1_net_debt_ebit_max(self) -> float:
        return {"strict": 3.0, "standard": 4.0, "loose": 6.0}[self.risk_sensitivity]

    @property
    def r1_interest_coverage_min(self) -> float:
        return {"strict": 4.0, "standard": 3.0, "loose": 2.0}[self.risk_sensitivity]

    @property
    def r1_current_ratio_min(self) -> float:
        return 1.0

    @property
    def r2_cfo_ni_consec_below_07_max(self) -> int:
        """允许的最大连续 < 0.7 年数，超过则触发 R2"""
        return {"strict": 1, "standard": 2, "loose": 3}[self.risk_sensitivity]

    @property
    def r2_fcf_neg_5y_max(self) -> int:
        """5 年内 FCF<0 允许的最大年数"""
        return {"strict": 2, "standard": 3, "loose": 4}[self.risk_sensitivity]

    @property
    def r3_share_cagr_5y_max(self) -> float:
        """5Y 股本 CAGR 上限"""
        return {"strict": 0.02, "standard": 0.03, "loose": 0.05}[self.risk_sensitivity]

    @property
    def v_pe_strict(self) -> float:
        """V2 严格模式 PE 上限（PRD 14.9）"""
        return 14.9

    @property
    def v_pe_standard_top(self) -> float:
        """V3 标准模式顶级公司 PE 上限（10Y 强通过 + 低风险）"""
        return 22.0

    @property
    def v_pe_standard_passed(self) -> float:
        """V3 标准模式 5Y 通过公司 PE 上限"""
        return 18.0

    @property
    def v_pe_standard_other(self) -> float:
        return 15.0


# 预设的几个完整配置示例
PRESET_STRICT = ScreenConfig(
    risk_sensitivity="strict",
    valuation_mode="strict",
)

PRESET_STANDARD = ScreenConfig(
    risk_sensitivity="standard",
    valuation_mode="standard",
)

PRESET_LOOSE = ScreenConfig(
    risk_sensitivity="loose",
    valuation_mode="loose",
)
