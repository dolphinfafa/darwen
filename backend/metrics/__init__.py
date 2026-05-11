# -*- coding: utf-8 -*-
"""Darwen V2 指标预计算引擎。

按 PRD 第 4 节严格口径，将 fact 表的财务原始字段转换为 canonical 指标，
落库到 metric_periodic 表，同步血缘到 metric_lineage_log。

模块结构：
- field_map  : canonical → source_type → [concept 候选列表]
- helpers    : 单点查询 + 序列查询 + 数据源路由
- roce       : ROCE / CapitalEmployed / EBIT
- leverage   : net_debt / interest_coverage / current_ratio
- cash_quality: CFO/NetIncome / FCF
- dilution   : share_count_cagr
- valuation  : pe_ttm / ev_ebit
- compute    : 调度入口 + 全量回填
"""
