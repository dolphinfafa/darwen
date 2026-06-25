# 2026-06-26 工作日志：A股股票池扩容（50 → 1800）+ 全量下游回填

## 主题：A股从硬编码 50 只蓝筹扩到沪深300+中证500+中证1000 全成分

此前 A股池仅 `universe.py` 硬编码 50 只（沪深300 子集），与美股 548 家严重失衡，
导致行业 peer 对标因同行业样本 <5 大多跳过、商业/治理统计代表性不足。本次拉全三大指数成分。

## 1. 扩池入库 `scripts/expand_cn_universe.py`

- 从 Tushare `index_weight` 取 **沪深300(300) + 中证500(500) + 中证1000(1006)** 最新成分，去重 **1800 只**。
- 对尚未完整入库的（跳过已有 fact 的公司，**可恢复**）调 `ingest_one_stock`：
  公司信息 + 利润表/资产负债表/现金流 + 披露日期 + 12 年日线行情 + 公告。
- 限速 0.35s/股 + 限频指数退避重试（10/20/40s）。
- **结果：1747 只新股全部入库成功，0 失败**；CN_A 由 50 → **1800 家**。耗时约 3 小时（12 年日线为瓶颈）。

> 筛选 universe 由 `api/screening._resolve_universe` 直接取 DB 全部 CN_A 公司，入库即自动扩池，无需改前端/引擎。

## 2. 下游全量回填 `scripts/backfill_cn_downstream.py`

入库后顺序回填，让新股立即可进三层漏斗：

| 步骤 | 结果 |
|---|---|
| 指标预计算 `persist_all_metrics_bulk`（ROCE/杠杆/现金质量/风险/偿付/稀释/估值） | 1800/1800 成功，0 错误（32.2 万年度行 / 48.5 万血缘行；pass_5y=438、strong=614）|
| 行业 peer 重建 `compute_industry_peer_stats`（全市场） | 1989 家、**103 个有效行业组**（原仅 32；A股 `rev_growth_vs_industry` 覆盖 ~12 → **1708 家**）|
| 治理硬事实 `ingest_pledge_signals` + `ingest_manager_changes` | 质押 19.8 万条/1597 家；管理层 exec_departure 4763 条/1402 家 |
| 商业 segment HHI `backfill_cn_segment_hhi`（fina_mainbz） | 1337 家 / 9914 期 |

## 3. 关键坑（已修）

`tushare_segment._hhi_from_items`：Tushare `bz_sales` 偶有 NaN，`int(round(NaN,-3))` 抛 `ValueError`
导致 segment HHI 步骤中断。修复加 `v != v`（NaN）跳过；补单测 `test_cn_hhi_handles_nan_and_dedup`。

## 4. 验证

- **指标覆盖**：A股 ROCE 1800/1800、应计 1800、net_debt 1756、行业 peer 1708。
- **端到端三层漏斗**（抽样新股，AI off）：ROCE→稳健→风险逐层正常判定，commercial(segment HHI)/
  治理硬事实(质押/管理层)均生效（如安集科技 ROCE+稳健+风险全过 = 入选候选）。
- 单测 20 项全过。

## 最大收益

**行业 peer 对标从"形同虚设"变为真正可用**：A股同行业样本充足，`rev_growth_vs_industry` 覆盖
从约 12 家跃升至 1708 家，稳健层「行业相对落后」判定对 A股全面生效。
治理（质押/管理层）、商业（segment HHI）统计也获全市场代表性。

## 关键文件

| 改动 | 路径 |
|---|---|
| 扩池入库 | `scripts/expand_cn_universe.py` |
| 下游回填 | `scripts/backfill_cn_downstream.py` |
| NaN 修复 | `backend/pipeline/commercial/tushare_segment.py` |
| 单测 | `tests/test_commercial_extract.py`（+2 A股 HHI 用例） |

## 后续可选

- 行情数据量大增（1800×12 年日线），如需可评估 market_bar 表体积/索引。
- 美股目前 548 家，可对称考虑扩到完整 S&P 500 / Russell 1000。
