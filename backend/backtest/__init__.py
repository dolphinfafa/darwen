# -*- coding: utf-8 -*-
"""Darwen V2 回测模块（PRD 第 8 节）。

P0 提供两类实验：

1. **Bucket Spread**（核心验证指标）
   bucket_spread.run(run_id, forward_end) 对一次已完成的 screen_run
   取每家公司在 run.as_of_date 与 forward_end 之间的回报，按 5 状态分桶
   统计 mean / median / win rate / count。

2. **月度滚动回测（v2_engine.py, P1）**
   在历史 N 个月每个 rebalance date 跑漏斗 → 候选等权组合 → 计算净值。
   依赖严格点时的指标重算，M7 v1 暂不实现，留接口骨架。

3. **指标评估** metrics_eval.py：CAGR / Sharpe / MDD / Win Rate 工具函数。
"""
