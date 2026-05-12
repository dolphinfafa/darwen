# -*- coding: utf-8 -*-
"""Darwen V2 三层漏斗筛选引擎（PRD 第 5/6/7/8 节）。

模块结构：
- reason_codes : 原因码常量定义
- config       : 阈值默认值（strict / standard / loose 三模式）
- exclusion    : Q0 非适用证券排除
- q_layer      : Q1-Q6 质量层
- r_layer      : R1-R12 风险层（M3 阶段硬规则；AI 占位由 M4 接入）
- v_layer      : V1-V5 价格层
- status_resolver : 五状态裁决
- funnel       : 顶层调度 run(universe, config, as_of_date, run_id, user_id)
"""
