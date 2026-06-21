# Darwen 项目进度总览

> 最后更新：2026-06-21
> 项目方向：V2 股票筛选系统（基于 Pulak Prasad《What I Learned About Investing from Darwin》）

---

## 项目状态：ROCE → 稳健性 → 风险性 三层全自动漏斗（2026-06-20 起取消人工 gate；架构始于 2026-06-18）

底层 V2 工程 + 数据精修 + AI 调用沿用 2026-05-13 生产可用版本。

### 2026-06-18 三层漏斗重构（7 项产品需求）

| 需求 | 状态 | 交付 |
|---|---|---|
| ROCE 配置（阈值 + 回溯年数 3/5/7/10） | ✅ | q_layer 按 N 年现算（每财年去重），N=5 与旧口径等价 |
| 跳过"配置门槛"步骤 | ✅ | ROCE 内嵌选股页，`/config` 下线 |
| 三层漏斗 ROCE→稳健→风险 + 分层人工 gate | ✅ | `funnel_v2.py` + advance/manual/funnel 端点；去掉估值层 |
| 历史筛选页改股票池名称 | ✅ | `PATCH /v2/my-runs/{id}` + MyRuns 行内改名 |
| 详情页仅历史 ROCE + 过滤原因 + 出处 | ✅ | CompanyDetailV2 瘦身 + evidence 出处接口 |
| 详情页"进入我的股票池" | ✅ | `/v2/watchlists/add-company` + 入池面板 |
| 新增"我的股票池"页面 | ✅ | watchlist 模型/API/MyWatchlist.vue |

- AI 双层判定（稳健 4 类 + 风险 8 类）已接入 `analyze_layer`，mock 验证通过；真实调用待用户 key。
- 5 个 Alembic 迁移（加列/加表可回滚）；旧 Q/R/V 引擎保留 deprecated。
- 新建 pytest（15 用例，含 ROCE N=5 等价护栏）。详见 `milestones/2026-06-18.md`。

### 2026-06-19 AI 介入选项 + 漏斗 bug 修复 + PRD V2.1

- 新增「AI 介入」选项 `ai_mode`（off / key_stage 仅风险层 / full 稳健+风险层全程）。
- fix：漏斗页改按 run.status 判断，不再被残留 `layer_status=running` 卡死转圈；AI 调用独立 session 隔离。
- fix：funnel 端点兼容旧引擎数据（无 rejected_at_layer 但 status=Rejected 不误判入选）；修正 14 个历史 run 状态。
- PRD 同步到 V2.1。详见 `milestones/2026-06-19.md`。
- ~~待办：数据更新到 2025~~ → ✅ 已确认落库（`metric_periodic` 2025 覆盖 594 家，2026-06-20 核对）。

### 2026-06-20 漏斗全自动化 + 交接事项重做

- **三层漏斗改全自动连跑**：`auto_advance` 默认 true，过一层自动进下一层、通过风险层即入选；
  取消分层人工 gate，移除 `/advance`、`/manual` 端点 + 前端 `advanceLayer`/`manualAction` + gate UI。
- 筛选历史删除：`DELETE /v2/my-runs/{id}`（FK 顺序级联清子表）+ MyRuns 删除按钮（端到端验证通过）。
- 详情页 ROCE/EBIT/CapitalEmployed 表头 ⓘ 口径说明；原因标签接入全局 `.dtip` 悬浮释义。
- 数据核对：Rocket(US_0001805284) `is_excluded=0` 未生效（全表 598 家无一排除，但其 ROCE 历年全 NULL 会被 ROCE 层自然过滤）。
- **后两层有效性修复**：修证据检索点时 bug（AI 此前喂入证据为 0 裸判全 PASS）+ 后两层改 AI
  REVIEW/REJECT 出局（此前仅 REJECT），配合后两层现能基于真实证据有效过滤。
- **TTM 口径已评估、决定暂不做**：维持年报口径（as_of 2025-12-31 已是最新完整财年），避免季度
  噪声/数据口径风险，等 FY2026 年报齐备后按 SOP 推进。详见 `milestones/2026-06-20.md` 八节。

### 2026-06-21 「我的股票池」改造

- **取消分组**：`MyWatchlist.vue` 重写为单一平铺表格（合并所有池去重）；新增 `GET/DELETE
  /v2/watchlists/my-stocks`；详情页入池简化为一键加默认池。
- **展示最新收盘价 + 市盈率**：复用 `compute_valuation_snapshot`，最新价取 market_bar ≤today 最新。
- **PE 改真 TTM**：`valuation.py` `net_income_ttm` 由「年报代理」改为真 4 季 TTM（YTD 差分：最近
  完整财年 + 本年最新YTD − 去年同期YTD；缺季报降级标 `PE_TTM_ANNUAL_PROXY`）。新增 helper
  `get_fact_series_asof`。验证 AMD TTM=5.009B（非年报 4.335）。
- **设为首页**：`/` redirect → `/my-watchlists`，导航置首位。
- **按需拉取行情**：进详情页 / 我的股票池页面时拉最新收盘价（yfinance 批量 / Tushare，当天去重 + 容错），
  详情页头部新增展示最新价/PE；新增 `services/quote.py` + `market_data.ingest_us_latest(_bulk)`。
- **漏斗结果页交互**：`FunnelResults.vue` 三层改手风琴折叠面板 + 多维搜索过滤（代码/名称/所在层/市场/行业，
  命中自动展开）；纯前端。详见 `milestones/2026-06-21.md`。
- PRD 同步到 **V2.2**；本会话 8 提交（`6498ca5`/`0b262f2`/`cbe4d72`/`d5efaac`/`8f7bdfb`/`c50c302`/`6524b03`/`52fee38`）。详见 `milestones/2026-06-20.md`。

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
| M7 v3 (E6 点时偏差) | ✅ | pit_audit.py：lookback 0-180 CAGR 波动 <2pp，0vs120 差 1.68pp（相对 5.6%）几乎达标 PRD <5% 阈值 |
| M7 v3 (基准对比 / 行业中性化) | ⏳ 后续 | — |
| 数据修补 (A 股 close) | ✅ | Tushare daily_basic 重拉 50 家不复权 close + market_cap，茅台 PE 143x→24.7x |
| 数据修补 (金融股 shares + Q0) | ✅ | SEC 加 dei.EntityCommonStockSharesOutstanding + 多 security 选普通股 + 88 家 SIC 重设 instrument_type，JPM mc 55B→658B |
| 数据修补 (TSLA/NVDA 财年) | ✅ | company 加 fiscal_year_end_month，SEC submissions.fiscalYearEnd 权威填充，TSLA 3→12、NVDA 10→1 |
| reason_code 中文 label | ✅ | reason_labels.py 51 项映射 + 2 API + 前端 ReasonPill 组件（按 severity 着色 + layer 边框 + tooltip）|
| M4 真实 AI 调用 | ✅ | ChatGPT 走 apiyi gpt-4.1-mini，5 家公司 11.8s，Apple/NVDA/TSLA 股权稀释 → AI_MINORITY_SHAREHOLDER_RISK → REVIEW |

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
| market_bar | 1,731,000+ | 2008-2026，美股 742 + A 股 50（A 股已用 Tushare 不复权 + market_cap 修复） |
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
| 茅台 | 66.9% | 24.7x ✓ | 1914B ✓ | ✓ pass | 2026-05-13 已修 Tushare 不复权 |
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
- `milestones/2026-05-13.md` — A 股 close 不复权数据修补
- `milestones/2026-06-18.md` — 三层漏斗重构（ROCE→稳健→风险 / 分层 gate / 我的股票池）
- `milestones/2026-06-19.md` — AI 介入选项 + 漏斗 bug 修复 + PRD V2.1
- `milestones/2026-06-20.md` — 漏斗改全自动 + 筛选历史删除 + 表头/原因标签 tooltip + PRD V2.2

---

*本文件由 Agent 维护，反映项目最新状态。*
