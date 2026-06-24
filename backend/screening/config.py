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
    roce_lookback_years: int = 5        # ROCE 回溯窗口（用户可配 3/5/7/10；N=5 等价旧 5Y 口径）
    roce_count_required_5y: int = 4     # 5 年中 ≥ threshold 的年数（旧口径，N≠5 时按 ⌈0.8N⌉ 现算）
    roce_count_required_10y: int = 8    # 10 年中 ≥ threshold 的年数（Q4 强通过）
    min_list_years: int = 5             # Q6 上市年限
    min_fiscal_years: int = 5           # Q1 财年数

    # R 层敏感度（strict / standard / loose）— 阈值随之调整
    risk_sensitivity: str = "standard"

    # V 层估值模式
    valuation_mode: str = "strict"  # strict / standard / loose

    # AI provider
    ai_provider: str | None = None

    # AI 介入范围：off=不调AI（全规则/占位）| key_stage=仅风险层(关键阶段) | full=稳健层+风险层全程
    ai_mode: str = "off"

    # 兼容旧 R 层引擎；funnel_v2 改用 ai_mode / ai_enabled_for 判断
    enable_ai_risk_layer: bool = False

    def ai_enabled_for(self, layer: str) -> bool:
        """funnel_v2 各层是否调 AI：full=稳健+风险；key_stage=仅风险层；off=都不调。"""
        if self.ai_mode == "full":
            return layer in ("sturdiness", "risk")
        if self.ai_mode == "key_stage":
            return layer == "risk"
        return False

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

    # ---- 稳健层 hard/soft 软警告阈值（soft = 进入观察区但不出局；hard = 直接剔除）----
    @property
    def r1_net_debt_ebit_soft(self) -> float:
        """net_debt/EBIT 软警告下界（高于此但未达 hard 上限 → soft）"""
        return {"strict": 2.0, "standard": 2.5, "loose": 4.0}[self.risk_sensitivity]

    @property
    def r1_interest_coverage_soft(self) -> float:
        """利息保障软警告上界（低于此但未跌破 hard 下限 → soft）"""
        return {"strict": 6.0, "standard": 5.0, "loose": 3.5}[self.risk_sensitivity]

    @property
    def r2_fcf_neg_5y_soft(self) -> int:
        """近 5 年 FCF<0 软警告下界年数（高于此但未达 hard → soft）"""
        return {"strict": 1, "standard": 2, "loose": 3}[self.risk_sensitivity]

    @property
    def r_accruals_3y_hard(self) -> float:
        """近 3Y 应计利润率均值硬剔除阈值（>此 → hard，利润质量差/疑盈余操纵）"""
        return {"strict": 0.08, "standard": 0.10, "loose": 0.15}[self.risk_sensitivity]

    @property
    def r_accruals_3y_soft(self) -> float:
        """应计利润率软警告下界（介于 soft~hard → 观察区）"""
        return {"strict": 0.04, "standard": 0.05, "loose": 0.08}[self.risk_sensitivity]

    @property
    def r_fcf_cv_5y_hard(self) -> float:
        """近 5Y FCF/收入 变异系数硬剔除阈值（>此 → hard，现金流极不稳定）"""
        return {"strict": 0.8, "standard": 1.0, "loose": 1.5}[self.risk_sensitivity]

    @property
    def r_fcf_cv_5y_soft(self) -> float:
        """FCF 变异系数软警告下界（介于 soft~hard → 观察区）"""
        return {"strict": 0.4, "standard": 0.5, "loose": 0.8}[self.risk_sensitivity]

    # ---- 偿付/营运资本（solvency_v1：Altman Z / 营运资本增长领先 / CCC 恶化）----
    @property
    def r_altman_z_hard(self) -> float:
        """Altman Z'' 低于此 → hard（财务困境/破产风险）"""
        return {"strict": 1.8, "standard": 1.1, "loose": 0.5}[self.risk_sensitivity]

    @property
    def r_altman_z_soft(self) -> float:
        """Altman Z'' 低于此（但未跌破 hard）→ soft（灰区）"""
        return {"strict": 3.0, "standard": 2.6, "loose": 1.8}[self.risk_sensitivity]

    @property
    def r_wc_growth_lead_hard(self) -> float:
        """近 3Y 应收/存货增速领先营收均值高于此 → hard。
        盈余质量属黄旗（成长/并购/口径变化均会领先），hard 阈设高，仅极端虚增才单独剔除；
        多数走 soft，靠 soft 叠加升级。"""
        return {"strict": 0.30, "standard": 0.40, "loose": 0.60}[self.risk_sensitivity]

    @property
    def r_wc_growth_lead_soft(self) -> float:
        return {"strict": 0.05, "standard": 0.08, "loose": 0.12}[self.risk_sensitivity]

    @property
    def r_ccc_delta_hard(self) -> float:
        """近 3 年 CCC 恶化天数高于此 → hard（现金占用剧增）"""
        return {"strict": 90.0, "standard": 120.0, "loose": 180.0}[self.risk_sensitivity]

    @property
    def r_ccc_delta_soft(self) -> float:
        return {"strict": 20.0, "standard": 30.0, "loose": 45.0}[self.risk_sensitivity]

    # 软警告叠加升级：达到此条数视为结构性脆弱，升级为硬剔除
    @property
    def r_soft_stack_to_hard(self) -> int:
        return {"strict": 2, "standard": 3, "loose": 4}[self.risk_sensitivity]

    # ---- 风险层治理硬事实（governance_signal）----
    @property
    def risk_exec_departure_3y_hard(self) -> int:
        """近 3 年高管/董事离任·任命(8-K Item 5.02)次数 ≥ 此 → hard（管理层剧烈动荡）"""
        return {"strict": 4, "standard": 5, "loose": 7}[self.risk_sensitivity]

    @property
    def risk_exec_departure_3y_soft(self) -> int:
        return {"strict": 2, "standard": 3, "loose": 4}[self.risk_sensitivity]

    @property
    def risk_pledge_ratio_hard(self) -> float:
        """A股整体股权质押比例(%) ≥ 此 → hard（控股股东高质押，爆仓/掏空风险）"""
        return {"strict": 40.0, "standard": 50.0, "loose": 65.0}[self.risk_sensitivity]

    @property
    def risk_pledge_ratio_soft(self) -> float:
        return {"strict": 20.0, "standard": 30.0, "loose": 45.0}[self.risk_sensitivity]

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
