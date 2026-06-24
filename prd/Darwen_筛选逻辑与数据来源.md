# Darwen 股票筛选逻辑与数据来源

> 版本：对应 2026-06 现行实现（三层全自动漏斗）
> 方法论基底：Pulak Prasad《What I Learned About Investing from Darwin》
> 本文档描述「筛选怎么判」与「数据从哪来」，细节以代码为准（`backend/screening/`、`backend/metrics/`、`backend/pipeline/`）。

---

## 一、总览

Darwen 是一套**三层漏斗式**股票筛选系统，核心思想是「排除的艺术」——先找长期高质量的公司，再逐层剔除脆弱的、有风险红旗的，剩下的才是入选。

```
选股票池（内嵌 ROCE 阈值 + 回溯年数）→ 点时数据
        ▼
① ROCE 门槛（规则）         ──自动──┐  长期资本回报优质
        ▼                            │
② 稳健性筛选（规则 + AI）   ──自动──┤  财务稳健 + 无脆弱特质
        ▼                            │
③ 风险性筛选（AI）          ──自动──┘  无管理层/治理红旗
        ▼
最终入选（通过全部三层）
```

- **全自动连跑**：过一层自动进下一层，通过第三层即入选，无人工 gate（2026-06-20 起）。
- **存活集语义**：`screen_result.rejected_at_layer IS NULL` 即当前存活/最终入选；某层不通过则标记被该层过滤。
- **估值（PE）不作为独立漏斗层**，降级为详情页参考信息。

---

## 二、第一层：ROCE 门槛（规则）

衡量「长期资本回报是否优质」。代码：`backend/metrics/roce.py`、`backend/screening/q_layer.py`。

### 2.1 ROCE 公式（严格按原著口径）

```
ROCE_t = EBIT_t / CapitalEmployed_t
CapitalEmployed = 净营运资本（剔除超额现金）+ 固定资产净值
                = (经营性流动资产 − 经营性流动负债) + 净 PPE
经营性流动资产 = 流动资产 − 现金 − 短期投资
经营性流动负债 = 流动负债 − 短期债务 − 一年内到期长债 − 流动租赁负债
```

- **EBIT**：美股取 `OperatingIncomeLoss`；A股三级回退（直接 EBIT → 营业利润+利息 → 利润总额+利息）。
- 资本占用 ≤ 0 时 ROCE 置 None 并标 `NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED`（走人工覆核语义，不算通过）。

### 2.2 判定（按 N 年「现算」）

- 用户在选股页配置：**ROCE 阈值**（默认 20%）+ **回溯年数 N**（默认 5，可配 3/5/7/10）。
- 现场从逐年 ROCE 算：近 N 年**中位数 ≥ 阈值** 且 **至少 ⌈0.8N⌉ 年达标**（如 N=5 需 ≥4 年 ROCE≥20%）。
- 近 2N 年同时满足 → 标 `q_strong_track`（10Y 强通过）。
- 财年数 < N → `Q1_INSUFFICIENT_HISTORY`；近 N 年 ≥2 年负/缺资本 → `Q5` 覆核。

### 2.3 Q0 排除（进入 ROCE 层前）

`backend/screening/exclusion.py`：以下不适用 ROCE 口径，直接排除——
- 手动标记 `company.is_excluded`；
- 按 `instrument_type` 排除：银行、保险、券商/经纪、REIT、ETF、基金、SPAC 等非适用证券。

---

## 三、第二层：稳健性筛选（规则 + AI）

衡量「公司是否具备稳健特质」。代码：`backend/screening/funnel_v2.py::_eval_sturdiness`。

### 3.1 规则部分：无负债 · 有充裕现金流

| 指标 | 阈值（strict / standard / loose） | 触发标签 |
|------|-----------------------------------|----------|
| net_debt / EBIT | > 3.0 / 4.0 / 6.0 | `STURDINESS_HIGH_DEBT` |
| 利息保障倍数 | < 4.0 / 3.0 / 2.0 | `STURDINESS_WEAK_COVERAGE` |
| 近 5 年 FCF<0 年数 | > 2 / 3 / 4 | `STURDINESS_NEGATIVE_FCF` |

任一规则 fail 即不通过该层（指标缺失则跳过该条，不算 fail）。

### 3.2 AI 部分：4 类「不稳健」信号

由 AI 判定（`ai/orchestrator.analyze_layer(layer="sturdiness")`），命中即扣分：
- `customer_concentration_risk` 客户不够多元（如 top1>25% 或 top5>50%）
- `supplier_concentration_risk` 供应商不够多元
- `disruption_risk` 行业变化快
- `management_instability` 管理团队不稳定

> 「竞争壁垒高」由 ROCE 代理（高 ROCE 即壁垒），不单列 AI 标签。

---

## 四、第三层：风险性筛选（AI）

排除「管理层/治理红旗」。代码：`_eval_risk` + `ai/orchestrator.analyze_layer(layer="risk")`。8 类红旗：

| 标签 | 含义 |
|------|------|
| `governance_risk` | 管理层不诚信 · 治理（董事会冲突、关联交易、控制权异常） |
| `accounting_risk` | 管理层不诚信 · 会计（财务重述、舞弊迹象） |
| `regulatory_risk` | 管理层不诚信 · 监管（处罚、立案、问询） |
| `turnaround_risk` | 重大转型/反转陷阱 |
| `serial_acquirer_risk` | 疯狂并购 |
| `speculative_guidance_risk` | 靠预测未来（过度依赖远期指引） |
| `stakeholder_unfriendly` | 对员工/客户/供应商不友好 |
| `minority_shareholder_risk` | 对少数股东不友好（如过度稀释） |

---

## 五、出局/通过规则（AI 裁决融合）

AI 对每只给一个 `overall_action`，四档语义递进：

| 动作 | 含义 | 后两层处理 |
|------|------|-----------|
| `PASS` | 无中/高风险 | **通过** |
| `MONITOR` | 有轻微迹象但不阻止继续研究 | **通过** |
| `REVIEW` | 中/高风险，需复核 | **出局** |
| `REJECT` | 确凿（≥0.8 置信 + 法定披露/硬规则） | **出局** |

- 稳健层：`(规则未 fail) 且 ai_action ∈ {PASS, MONITOR, 未跑AI}` 才通过。
- 风险层：`ai_action ∈ {PASS, MONITOR}` 才通过；未跑 AI（未启用/未绑 key）→ 占位放行 `RISK_PENDING_AI`。
- **REJECT 融合门槛极高**：需高置信（≥0.8）且有法定披露佐证或硬规则同向触发，否则降级 REVIEW。
- AI 介入范围可配（`ai_mode`）：`off`（纯规则）/ `key_stage`（仅风险层）/ `full`（稳健+风险层）。

### AI 证据来源（点时严格，只取 as_of 之前可见的）

- **美股**：SEC 法定披露（10-K / 10-Q / 8-K，`text_document`）+ Polygon 个股新闻。
- **A股**：Tushare `anns_d` 个股公告（年报/季报/监管/诉讼等，含巨潮原文链接）。
- 取数 `orchestrator._load_recent_documents`：先按点时（`published_at ≤ as_of`）过滤再取最近若干份（喂标题 + 正文摘要）。

---

## 六、估值（PE，详情页参考，不作漏斗层）

- `pe_ttm = 市值 ÷ 真 TTM 净利润`。
- **真 TTM 净利润（YTD 差分法）**：净利润是年初至今累计，故 `TTM = 最近完整财年 + 本年最新YTD − 去年同期YTD`；季报不足时降级回最近年报（标 `PE_TTM_ANNUAL_PROXY`）。
- 参考阈值（PRD V 层，现仅展示不闸断）：严格 PE≤14.9；标准 顶级≤22 / 通过≤18 / 一般≤15。

---

## 七、数据来源

### 7.1 美股

| 用途 | 来源 | 落库 |
|------|------|------|
| 财务（资产负债/利润/现金流） | **SEC EDGAR XBRL**（companyfacts） | `fact` 表 |
| 公司信息 / 财年末 | SEC submissions | `company` |
| 行情 OHLCV | **yfinance**（按需拉最近 5 日 `ingest_us_latest`） | `market_bar` |
| 市值 | 自算 `close × shares_outstanding`（yfinance 不直接给） | — |
| AI 证据：法定披露 | SEC filing 文本（10-K/10-Q/8-K） | `text_document` / `filing` |
| AI 证据：新闻 | **Polygon News** | `text_document` |
| 财报出处链接 | SEC filing `url_pdf`（`/v2/company/{id}/filing-url` 302→SEC 原文） | `filing` |

### 7.2 A股

| 用途 | 来源（Tushare Pro 接口） | 落库 |
|------|--------------------------|------|
| 财务三表 | `income` / `balancesheet` / `cashflow` | `fact` |
| 公司信息 | `stock_basic` | `company` |
| 行情 OHLCV | `daily`（按需拉最近 `ingest_daily`） | `market_bar` |
| 市值 + PE | `daily_basic`（`total_mv` 万元 → 元；权威市值） | `market_bar` |
| 财报披露日期（点时可见性） | `disclosure_date` | `filing` |
| 个股公告（年报/季报/监管） | `anns_d`（含巨潮 detail 直链） | `text_document` |
| 财报出处链接 | 上述 anns_d 年报公告 → 详情页 `cn_filings` 逐年巨潮直链 | `text_document` |
| 市场资讯（全市场大盘） | `major_news`（非个股，仅市场背景展示） | `market_news` |

> A股「资讯」局限：Tushare 无「按个股」的新闻流；个股动态靠 `anns_d` 公告，大盘资讯走 `major_news`（市场资讯页）。

---

## 八、指标计算引擎

代码：`backend/metrics/`。从 `fact`（原始财务）算出 `metric_periodic`（指标）。

- **formula_version 分模块共存**：`roce_v1`（ROCE/EBIT/资本占用等）、`leverage_v1`（净负债/利息保障）、
  `cash_quality_v1`（CFO/NI、FCF）、`dilution_v1`（股本 CAGR）、`valuation_v1`（市值/PE/EV）。便于口径升级并存。
- **点时可见性（避免未来函数）**：三轨——`accepted_date ≤ as_of` ＞ `available_date ≤ as_of` ＞
  `period_end + 披露 lag(默认120天) ≤ as_of`。筛选只用 `as_of` 之前可见的数据。
- **年报口径**：ROCE 等用完整财年（`annual_only`，按 `fiscal_year_end_month` 匹配），避免季报噪声。
- **as_of 默认 2025-12-31**（最新完整财年）；TTM 口径仅用于 PE 的净利润分母。

---

## 九、行情新鲜度（按需拉取）

- 进「股票详情页 / 我的股票池页面」时按需拉最新收盘价（`services/quote.py::refresh_quotes`）：
  选主 security → **当天去重**（已是最新则跳过）→ 美股批量 yfinance / A股逐个 Tushare → 全程容错。
- 展示「最新收盘价 + 交易日」：交易日标明价格截止哪天（当日未拉到则停在库内最近交易日，不会变成今天）。

---

## 十、对外接口（MCP）

- 外部 AI agent（Claude）可凭 per-user 令牌连远程 MCP（`backend/mcp_server.py`，`/v2/mcp`），
  工具 `list_watchlist_quotes` 读「我的股票池」最新价 + 市盈率，用于到价提醒（目标价/提醒由 agent 侧判断）。

---

## 附：关键代码索引

| 模块 | 路径 |
|------|------|
| 三层漏斗引擎 | `backend/screening/funnel_v2.py` |
| ROCE 层判定 | `backend/screening/q_layer.py`、`backend/metrics/roce.py` |
| Q0 排除 | `backend/screening/exclusion.py` |
| 阈值配置 | `backend/screening/config.py` |
| AI 编排 / 融合 | `backend/ai/orchestrator.py`、`backend/ai/schema.py` |
| 指标计算 | `backend/metrics/`（compute / helpers / roce / leverage / cash_quality / valuation） |
| 估值（真 TTM PE） | `backend/metrics/valuation.py` |
| A股数据接入 | `backend/pipeline/cn_stock_v2/tushare_client.py` |
| 美股行情 | `backend/pipeline/market_data.py` |
| 行情按需刷新 | `backend/services/quote.py` |
