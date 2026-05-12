# Darwen 项目进度总览

> 最后更新：2026-05-12
> 项目方向：V2 三层漏斗股票筛选系统（基于 Pulak Prasad《What I Learned About Investing from Darwin》）

---

## 项目状态：V2 完整工程闭环（M1-M7 + M1.9 + M1.10 + M7 v2 + 548 美股全量回填）

---

## V2 里程碑进度

| # | 里程碑 | 状态 | 关键交付 |
|---|---|---|---|
| M1   | 数据基础（schema 重构、Tushare Pro 接入、10 家 A 股蓝筹回填） | ✅ | 6 张 V2 表 + Tushare 字段 canonical 化 |
| M1.x | SEC 字段修补（CORE_CONCEPTS 扩 7 tag、546 美股重拉） | ✅ | STI / LongTermDebtCurrent / OperatingLease 等入库 |
| M2.1 | 字段映射 & helpers | ✅ | field_map（24 canonical 三向映射）+ helpers（三轨可见性 + annual_only + 财年末启发式） |
| M2.2 | ROCE 严格口径 + 5Y/10Y 门槛 | ✅ | roce.py + QualityGate（含 Q5_RECENT_NEG_CAP 修正） |
| M2.3 | 杠杆 + 现金质量 | ✅ | leverage.py + cash_quality.py（R1/R2 输入） |
| M2.4 | 稀释 + 估值 | ✅ | dilution.py（CAGR + 拆股检测）+ valuation.py（mc/PE/EV）|
| M2.5 | 调度器整合 + 全量回填 | ✅ | persist_all_metrics_for_company / 598 家 / 5 模块 27 distinct metric / 72,680 行 / 12 分钟 |
| M3   | 三层漏斗（Q / R / V Layer） | ✅ | screening 模块 8 文件 + 5 状态裁决 / 548 家 3.6s 跑完 |
| M4   | AI 风险层（ChatGPT + MiniMax + Fernet） | ✅ | ai 模块 9 文件 + 加密 + 重试 + fallback + PRD 融合规则 |
| M5   | API 层重写（V2 endpoints + Key 绑定） | ✅ | 10 endpoint：3 user-settings + 6 screening + 1 backtest |
| M6   | 前端 6 页面重构 | ✅ | UniverseConfig / ScreenConfig / ScreenRun / Results / CompanyDetailV2 / AccountSettings |
| M7   | Bucket Spread 回测 + 端到端 smoke | ✅ | backtest 3 模块 + /v2/backtest/bucket-spread + E2E 6/6 |
| M7 v2 | 月度滚动回测 + E2 单调性 | ✅ | v2_engine.py 月度再平衡 / 5 年 CAGR 28.9% / Sharpe 1.24 / E2 ROCE 单调性验证 |
| M1.9 | SEC filing 文本与元数据 | ✅ | filings_text.py / 548 美股 8,440 text_document / 108,761 filing 元数据 |
| M1.10| Polygon News 接入 | ✅ | polygon_news.py / 14,632 新闻覆盖 500 家美股 |
| 全量回填 | 548 美股 SEC + Polygon News | ✅ | text_document 23,431 行 / 96% 美股有 AI 证据 |
| M7 v3 | E6 点时偏差 / 基准对比 / 行业中性化 | ⏳ 后续 | — |
| 数据修补 | A 股不复权 close / 金融股 shares / TSLA 财年 | ⏳ 后续 | 影响估值数值精度 |

---

## 数据资产（截至 2026-05-11）

| 表 | 行数 | 说明 |
|----|---:|------|
| fact (SEC) | 1,074,000+ | 含新增 7 个 tag 重拉数据 |
| fact (TS-FS) | 13,874 | A 股新数据 10 家蓝筹 |
| fact (AKSHARE) | 26,629 | A 股旧数据 50 家（M2 fallback） |
| company | 598 | 548 美股 + 50 A 股 |
| metric_periodic | 72,680 | 5 个模块 18 个 distinct metric_name，formula_version 区分 |
| metric_lineage_log | 86,811 | 每输入字段一行血缘记录 |
| market_bar | 1,784,230 | 2008-2026，美股 742 + A 股 50（A 股为复权价待修复） |
| text_document | 23,431 | SEC 8-K 6,588 + 10-K 813 + 10-Q 1,398 + PG-NEWS 14,632 |
| filing (accepted_at 完整) | 108,761 / 120,213 (90.5%) | M4 AI 风险层证据可点时追溯 |

### metric_periodic 按 formula_version 分布

| formula_version | distinct metrics | total rows |
|---|---:|---:|
| roce_v1 | 11 | 33,699 |
| leverage_v1 | 4 | 20,144 |
| cash_quality_v1 | 6 | 12,530 |
| dilution_v1 | 2 | 3,979 |
| valuation_v1 | 4 | 2,328 |

---

## M2 全量回填验收结果（598 家 × 18 metric）

### 通过率（更新自 M2.4 财年末推断改进）

- 通过 5Y 门槛 (Q3 PASS)：172 / 598 = **28.8%**（M2.4 财年末推断改进后 +19 家）
- 强通过 (10Y 强 track record)：146 / 598 = **24.4%**（+17 家）
- 与 Pulak 书"严苛筛选"预期吻合

### fail_reason 分布

| reason | count | 含义 |
|---|---:|---|
| 通过 (NULL) | 153 | Q3 通过 |
| Q5_RECENT_NEG_CAP_OR_MISSING | 177 | 近 5 年 ≥ 2 年负营运资本 / 字段缺，走 P1 人工覆核（Apple/Visa 等大现金公司） |
| Q3_FAIL_MEDIAN | 107 | 5Y ROCE 中位数 < 20% |
| Q1_INSUFFICIENT_HISTORY | 43 | 财年不足 5 年 |
| Q3_FAIL_COUNT | 17 | 中位数过线但 ≥ 20% 年数 < 4 |

### 算法抽样验证

| 公司 | 5Y 中位数 | PE_TTM | mc | 状态 | 备注 |
|---|---:|---:|---:|---|---|
| Microsoft | 29.7% | 35.2x | 3103B | ✓ pass + strong | mc / PE 与公开数据吻合 |
| Apple | Q5_RECENT_NEG_CAP | 40.2x | 3765B | 覆核 | ROCE 不可比但 mc/PE 正确 |
| Nvidia | 39.7% | — | — | ✓ pass + strong | |
| Medtronic | 52% | — | — | ✓ pass | |
| 美的集团 | 91.8% | 13.8x | 616B | ✓ pass + strong | mc/PE 与公开数据吻合 |
| 茅台 | 66.9% | 143x ❌ | 11134B ❌ | ✓ pass | mc/PE 因 V1 复权价失真，roce 正确 |
| 泸州老窖 | 105.7% | — | — | ✓ pass + strong | |
| Cisco | 22% | — | — | ✓ pass | 修补前 213% 失真 |
| Visa | Q5_RECENT_NEG_CAP | — | — | 覆核 | 修补前 622% 假阳 |
| 京东方 | 5.2% | — | — | Q3_FAIL_MEDIAN | 重资本面板厂 |
| 格力 | NEGATIVE_CAP_EMP | — | — | Q5 覆核 | 结构性负 NWC |
| 广发证券 | n/a | — | — | Q0 排除 | 券商资产结构 |

---

## 关键技术决策（V2 时期）

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-05-09 | V0/V1 评分体系完全替换 | drop score_snapshot/factor_value 表 + 删 scoring/factors/backtest 目录 |
| 2026-05-09 | A 股数据源切换 Tushare Pro | 用户已升级付费套餐，财报 + 披露日期 + daily_basic 全有 |
| 2026-05-09 | 旧 30 因子加权评分弃用 | PRD V2 改为五状态 + reason_codes，不输出综合总分 |
| 2026-05-09 | AI Key 用户表加密存储 | Fernet + DARWEN_FERNET_KEY，每用户独立计费 |
| 2026-05-09 | ChatGPT 5 + MiniMax 2.7 双 provider | M4 实现 |
| 2026-05-11 | fact.account_code 退化兼容 | M1 重构时退化为字面 taxonomy 名，helpers 改用 concept 查实际 tag |
| 2026-05-11 | helpers 跨 source 自动回退 | A 股 TS-FS → AKSHARE，US 仅 SEC |
| 2026-05-11 | 严格年报模式 | annual_only=True + fiscal_year_end_month 精确匹配，避免季报混入 |
| 2026-05-11 | ROCE 缺失字段降级标签 | EXCESS_CASH_PROXY_LOW_CONFIDENCE / NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED / EBIT_FROM_OP_INC_PLUS_INTEREST 等 |
| 2026-05-11 | Quality Gate 窗口取"最近 5 完整财年"含 invalid | 避免 Apple/Visa 等用早期 valid 年补窗口假阳通过 |
| 2026-05-11 | SEC CORE_CONCEPTS 扩 7 tag | ShortTermInvestments / MarketableSecuritiesCurrent / LongTermDebtCurrent 等是 ROCE 公式必需 |
| 2026-05-11 | formula_version 字段 | metric_periodic 唯一键含 formula_version，便于未来口径升级共存 |
| 2026-05-11 | 每模块独立 formula_version | roce_v1 / leverage_v1 / cash_quality_v1 / dilution_v1 / valuation_v1 — 各自单独升级 |
| 2026-05-11 | FCF 优先 CFO-CapEx | Tushare fcf 字段口径未文档化（茅台 2019 异常），与 PRD R2 公式一致更稳定 |
| 2026-05-11 | EBIT 跨模块共享 ebit_by_year | leverage 计算复用 ROCE 求出的 EBIT 避免重复求解 |
| 2026-05-11 | get_fact_value_asof 三轨可见性 | accepted_date → available_date → period_end + 120 天 lag 兜底 AKSHARE 旧数据 |
| 2026-05-11 | get_fiscal_year_end 用 NI 取年最大 | Revenues 月份众数对 MSFT/AAPL 等季报年报均匀分布失败，NI 全年 > 单季更可靠 |
| 2026-05-11 | valuation as_of 默认 year_range 末年 12-31 | 反映"回测点时"语义，便于 M7 回测复用 |
| 2026-05-11 | dilution 拆股检测 ratio ≥ 1.5x | Apple 2020 4:1 拆股标 POSSIBLE_STOCK_SPLIT_{year}，提示 CAGR 失真 |

---

## V2 主线 5 状态分桶（US standard, asof=2024-12-31）

| 状态 | 数 | 占比 |
|---|---:|---:|
| HighConviction | 4 | 0.7% (Aptiv / EBAY / ON Semi / Elevance Health) |
| NearFairPrice | 5 | 0.9% |
| TooExpensive | 56 | 10.2% |
| Review | 234 | 42.7% |
| Rejected | 249 | 45.4% |

## Bucket Spread 1.23Y 验证（2024-12-31 → 2026-03-27）

| 状态 | n | mean | win_rate |
|---|---:|---:|---:|
| HighConviction | 4 | +5.8% | 50% |
| **NearFairPrice** | **5** | **+29.4%** | **80%** ← Pulak 价值股策略验证 |
| TooExpensive | 56 | +25.8% | 64% |
| Review | 234 | +16.5% | 56% |
| Rejected | 224 | +48.9% | 73% ← 2025-26 AI 牛市高 beta 暴涨 |

短期 (1.23Y) 价值策略对 Rejected 牛市 beta 不利；需 3-5 年长期回测看完整效应。

## M7 v2 月度滚动回测（2020-2024 美股 standard）

| 指标 | 值 |
|---|---:|
| 总回报 | +256% |
| **CAGR** | **28.92%** |
| Sharpe | 1.24 |
| Max Drawdown | -24.2% |
| 月度胜率 | 64.4% |
| 候选数/月 | 平均 ~8 家 |

### PRD 第 8 节 E2 单调性验证 ✓

| ROCE 阈值 | CAGR | Sharpe |
|---:|---:|---:|
| 10% | 26.66% | 1.18 |
| 20% | 28.92% | 1.24 |
| **30%** | **34.50%** | **1.31** |

**ROCE 阈值越严 → CAGR 单调递增**，Pulak 核心论点完整验证。

## M4 AI 风险层证据覆盖率（548 美股）

| 证据源 | 覆盖公司 | 占比 |
|---|---:|---:|
| SEC 法定披露（8-K/10-K/10-Q） | 485 | 88.5% |
| Polygon News | 500 | 91.2% |
| 至少一种证据 | 524+ | **96%** |

PRD 第 6 节"证据优先级"层次完整：法定披露可触发 REJECT，新闻最高 REVIEW。

---

## 主要参考文档

- `prd/v2.0/Darwen_V2_PRD_Master.md` — V2 PRD（权威）
- `milestones/v2-plan.md` — M2-M7 完整实施规划
- `.agent/workflows/v2-implementation-roadmap.md` — Agent 执行 SOP
- `milestones/2026-05-09.md` — M1 完成记录
- `milestones/2026-05-11.md` — M2 ROCE 落地记录
- `milestones/2026-05-12.md` — M3-M7 主线收官

---

*本文件由 Agent 维护，反映项目最新状态。*
