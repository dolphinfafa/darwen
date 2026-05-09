# Darwen V2.0 PRD — 三层漏斗股票筛选系统

**版本**：2.0
**生效日期**：2026-05-09
**方法论基底**：Pulak Prasad《What I Learned About Investing from Darwin》(2023)
**相对 V1.0 的差异**：完全替换 30 因子加权与 4 层漏斗评分体系

---

## 执行摘要

本 PRD 将 Darwen 项目重写为一套**三层漏斗式股票筛选系统**：

1. **第一层（质量层）**：先筛"长期优质公司"，核心门槛 **过去 5 年 ROCE 中位数 ≥ 20% 且 4/5 年 ≥ 20%**
2. **第二层（风险层）**：自动硬规则 + AI 风险标签器（ChatGPT 5 / MiniMax 2.7）过滤重大财务/治理/商业/行业风险
3. **第三层（价格层）**：以 **TTM PE 14.9x** 为默认严格买入锚，标准模式分级放宽

**关键产品决策**：

- **不输出全市场综合总分**；输出 `Rejected / Review / Too Expensive / Near Fair Price / High Conviction` 五状态 + 原因码 + 风险标签 + 证据链接
- **不将新闻直接改写长期质量分**；新闻/公告/文本默认进入"风险标签层"
- **金融、保险、券商、REIT、基金、ETF、SPAC、壳公司**在 v1 默认排除（书中 ROCE 口径不适用）
- **ROCE 严格按书中思路**：EBIT / (净营运资本〔剔除超额现金〕+ 固定资产净值)
- **用户可自定义股票池、ROCE 门槛、风控敏感度与价格阈值**
- **点时回测**必须以 filing/公告实际可见时间为准

---

## 一、产品目标与非目标

### 1.1 产品目标

1. 用**长期历史 ROCE**筛出优质公司
2. 过滤掉**重大财务、治理、商业、行业风险**
3. 仅在**价格合适**时进入可买入候选
4. 单股输出必须**可追溯到字段、来源、时间点、AI 证据和人工覆盖记录**

### 1.2 非目标

- 不做日内/短线交易信号
- 不做预测驱动的 DCF 主模型
- 不做"新闻情绪直接改长期质量分"
- 不在 P0 覆盖银行、保险、券商、REIT、ETF、封闭式基金、SPAC
- 不在 P0 生成自动下单指令

### 1.3 范围与优先级

| 优先级 | 范围 |
|---|---|
| **P0** | 股票池构建、点时数据层、ROCE 引擎、优质公司筛选、风险过滤、价格闸门、结果页、单股报告、日志追溯、回测框架 |
| P1 | 完整人工覆核工作流、AI 从公告抽取客户/供应商集中度、行业扰动标签、历史估值分位、预警订阅 |
| P2 | peer cluster / outside view、智能问答、组合层归因、更多商业数据源适配 |

---

## 二、用户角色

| 角色 | 能力 |
|---|---|
| 普通用户 | 新建股票池、设置门槛、执行筛选、查看结果、保存观察列表 |
| 研究员/审核员 | 查看证据、覆核 AI 结果、手动改状态、填写备注（P1） |
| 管理员 | 配置数据源优先级、提示词版本、阈值默认值、字段映射、模型路由 |

---

## 三、核心流程

```
1. 股票池构建 ──→ 2. 点时数据拉取 ──→ 3. 优质公司筛选（Q-Layer）
                                          │
                                          ▼
                                       通过 → 4. 风险过滤（R-Layer：硬规则 + AI）
                                                  │
                                                  ▼
                                               通过/Review → 5. 价格闸门（V-Layer）
                                                                │
                                                                ▼
                                                       6. 五状态输出
```

---

## 四、ROCE 计算（严格书中口径）

```text
ROCE_t = EBIT_t / CapitalEmployed_t

CapitalEmployed_t = NetWorkingCapitalExcessCash_t + NetFixedAssets_t

NetWorkingCapitalExcessCash_t = OperatingCurrentAssets_t - OperatingCurrentLiabilities_t

OperatingCurrentAssets_t = CurrentAssets_t - CashAndEquivalents_t - ShortTermInvestments_t

OperatingCurrentLiabilities_t = CurrentLiabilities_t
                                - ShortTermDebt_t
                                - CurrentPortionOfLongTermDebt_t
                                - CurrentLeaseLiability_t
```

### 字段口径规则

- **EBIT_t**
  - 美股优先：`OperatingIncomeLoss` / operating income
  - A 股优先：明确息税前利润字段；若无，用「营业利润 + 利息费用」近似；再不行用「利润总额 + 利息费用」
- **NetFixedAssets_t**
  - 默认只取 **净固定资产 / Net PPE**
  - **不计入** goodwill、商誉、长期股权投资、金融资产与大多数无形资产
- **ShortTermInvestments_t** — 缺失则置 0 + 打 `EXCESS_CASH_PROXY_LOW_CONFIDENCE=1`
- **CapitalEmployed_t ≤ 0** — 不自动排除；标 `NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED` 进入人工覆核

### 质量门槛工程化判定

- 最少 **5 个完整财年**
- **通过质量门槛**：5Y ROCE 中位数 ≥ 20% **且** 5 年中至少 4 年 ROCE ≥ 20%
- **强通过**（`STRONG_TRACK_RECORD`）：10Y 可得 ≥ 8 年 **且** 10Y 中位数 ≥ 20%

---

## 五、第一层：优质公司筛选规则（Q-Layer）

| ID | 规则 | 自动化判定 | AI 判断 | 默认动作 | P0/P1 |
|---|---|---|---|---|---|
| Q0 | 非适用证券排除 | 银行/保险/券商/REIT/ETF/SPAC/壳/优先股/ADR | 无 | 排除或转观察池 | P0 |
| Q1 | 财报历史完整性 | ≥ 5 完整财年；缺口 ≤ 1 年 | 无 | 不足则观察池 | P0 |
| Q2 | ROCE 逐年计算 | 严格按上文公式 | 无 | 生成年序列 | P0 |
| Q3 | 5 年质量门槛 | 5Y 中位数 ≥ 20% 且 4/5 年 ≥ 20% | 无 | 通过/排除 | P0 |
| Q4 | 10 年强通过标签 | 10Y 可得 ≥ 8 年且中位数 ≥ 20% | 无 | 打 `STRONG_TRACK_RECORD` | P1 |
| Q5 | 负/零资本占用处理 | `CapitalEmployed ≤ 0` | 是否结构性负营运资本优点 | 人工覆核 | P1 |
| Q6 | 上市时间不足 | 上市未满 5 年 | 无 | 观察池，不进主候选 | P0 |

---

## 六、第二层：风险过滤规则（R-Layer）

### 证据优先级

`法定披露/监管文书 > 交易所/巨潮公告 > 供应商结构化公告源 > 主流新闻 > 管理层采访/路演`

### 风险规则表

| ID | 风险维度 | 自动化判定 | AI 判断 | 默认动作 | P0/P1 |
|---|---|---|---|---|---|
| R1 | 财务脆弱性 | `interest_coverage < 3` 或 `net_debt/EBIT > 4` 或 `current_ratio < 1 且连续2年恶化` | 无 | 排除 | P0 |
| R2 | 利润质量差 | `CFO/NetIncome < 0.7` 连续 2 年；或 `FCF<0` 在 5 年中 ≥ 3 年 | 是否扩产/一次性 | 排除或覆核 | P0 |
| R3 | 高频稀释 | 5Y `share_count_cagr > 3%` 且 ROCE 未改善 | 是否高回报再投资 | 覆核/排除 | P0 |
| R4 | 并购成瘾 | 3Y 并购现金流占营收高、`goodwill/assets` 抬升、ROCE 下滑 | 是否整合后回报提升 | 覆核/排除 | P0 |
| R5 | 审计/会计问题 | 非标审计、否定/无法表示意见、重大重述 | 重述是否影响核心 | 排除或高优先覆核 | P0 |
| R6 | 监管/处罚 | 交易所监管函、立案调查、重大处罚 | 严重度、持续性 | 覆核/排除 | P0 |
| R7 | 客户集中 | 年报披露 top1>25% 或 top5>50% | 关系稳定性、单一项目 | 覆核 | P1 |
| R8 | 供应商集中 | 年报披露 top1>25% 或 top5>50% | 替代性、绑定 | 覆核 | P1 |
| R9 | 转型/反转陷阱 | 最近 1-2 年改善但 5Y 历史差 + restructuring/turnaround narrative | 转型真实性 | 覆核，默认不放行 | P0 |
| R10 | 管理层稳定性 | CEO/CFO 3 年内更迭 ≥ 2 次 | 离任原因、治理冲突 | 覆核 | P1 |
| R11 | 少数股东不友好 | 关联交易异常、资金占用、股权质押/冻结、低价定增 | 行为严重度 | 覆核/排除 | P1 |
| R12 | 行业/技术断裂 | 无可靠结构化硬规则 | 护城河被技术/监管打断 | 覆核 | P1 |

### AI 风险层（PRD 第 4.5 节）

#### Prompt 模板（核心）

```text
系统角色：
你是 Darwen 风险过滤器。你的任务不是推荐买卖，而是识别"是否存在应阻止继续研究或要求人工覆核的重大风险"。

输入：
1) 公司基础信息：ticker、市场、行业、主营业务摘要
2) 点时财务摘要：过去5年/10年 ROCE、现金流、杠杆、股本变化、并购、审计意见
3) 文档列表：按时间倒序给出公告/年报/监管函/新闻
4) 当前规则引擎已触发标签

任务：
A. 仅从输入证据中判断是否存在以下标签：
   governance_risk / accounting_risk / regulatory_risk / turnaround_risk /
   serial_acquirer_risk / customer_concentration_risk / supplier_concentration_risk /
   disruption_risk / minority_shareholder_risk
B. 对每个标签输出 severity（low/medium/high）、confidence（0-1）、evidence_doc_ids、short_reason
C. 输出 overall_action：PASS / REVIEW / REJECT / MONITOR
D. 若仅有新闻、没有法定披露支撑，最高只能给 REVIEW
E. 输出中文，不要生成买卖建议价位
```

#### AI 输出 JSON Schema

```json
{
  "ticker": "ABC",
  "market": "US",
  "as_of_date": "2026-05-09",
  "overall_action": "REVIEW",
  "summary_cn": "...",
  "labels": [
    {
      "label": "customer_concentration_risk",
      "severity": "medium",
      "confidence": 0.84,
      "evidence_doc_ids": ["doc_1021"],
      "short_reason": "..."
    }
  ],
  "manual_review_required": true
}
```

#### 融合规则

- `REJECT` 优先级最高，但需满足：高置信度 (`confidence ≥ 0.8`) **且** 证据为法定披露/监管文书 **或** 自动硬规则已触发
- `REVIEW`：任一中高风险标签触发；或文本结论与结构化结论冲突
- `PASS`：无高/中风险标签
- `MONITOR`：现阶段不排除但建议持续观察的事件型风险

---

## 七、第三层：价格筛选规则（V-Layer）

| ID | 规则 | 自动化判定 | 默认动作 | P0/P1 |
|---|---|---|---|---|
| V1 | 主估值指标 | `PE_TTM` 为主；若 EPS≤0，不进入买入状态 | 继续观察 | P0 |
| V2 | 默认严格模式 | `PE_TTM ≤ 14.9` | 可买入候选 | P0 |
| V3 | 默认标准模式 | 顶级（10Y强通过且风险低）放宽至 `PE_TTM ≤ 22`；标准 `≤ 18`；一般 `≤ 15` | 可配置 | P1 |
| V4 | 公司自身历史锚 | 若有 10 年估值，叠加 `PE_TTM ≤ 公司10年中位数` 或 `≤ 60分位` | 二级过滤 | P1 |
| V5 | 周期/临时盈利扭曲 | AI 识别 PE 失真 | 覆核 | P1 |

---

## 八、系统输出状态

| 状态 | 含义 | 触发条件 |
|---|---|---|
| `Rejected` | 直接排除 | 质量门槛未过；或重大硬风险触发 |
| `Review Required` | 人工覆核 | 质量通过，AI/规则触发中高风险或资本占用异常 |
| `Qualified but Too Expensive` | 合格但太贵 | 质量通过、风险可接受，但估值闸门未过 |
| `Qualified and Near Fair Price` | 合格且接近合理价 | 质量通过、风险可接受、价格接近买入区 |
| `High Conviction Candidate` | 高确信候选 | 强通过、低风险、价格达标、流动性达标 |

---

## 九、数据架构与核心表

### 标准表

| 表 | 用途 |
|---|---|
| `instrument_master`（company + security） | 证券主表 |
| `price_daily_pt`（market_bar） | 点时日线/估值价格表 |
| `financial_periodic_pt`（fact） | 点时财报表（period_end + accepted_date 版本） |
| `filing_event`（filing） | 法定披露/公告元数据 |
| `text_document` | 公告/新闻正文与摘要 |
| `risk_ai_result` | AI 风险标签输出 |
| `screen_run` | 筛选任务主表 |
| `screen_result` | 单次筛选结果表 |
| `manual_override_log`（P1） | 人工覆盖日志 |
| `metric_periodic` | 预计算指标 |
| `metric_lineage_log` | 字段来源追溯表 |

### 数据源

**美股**：
- 主源：urlMassive/Polygon（财报/比率/概览/float/news）
- 法定回查源：urlSEC EDGAR API
- 生产级增强（P2）：urlNasdaq Data Link

**A 股**：
- 主源：urlTushare Pro（财报/daily_basic/日线/披露日期/公告）
- 法定回查源：url巨潮资讯、url上交所/深交所公告
- 生产级增强（P2）：urlWind Server API、urliFinD

### 源代码表

| 代码 | 含义 |
|---|---|
| PG-FS | Massive/Polygon 财报 |
| PG-R | Massive/Polygon 比率 |
| PG-REF | Polygon Ticker Overview |
| PG-NEWS | Polygon News |
| SEC | SEC EDGAR |
| TS-FS | Tushare 财报 |
| TS-MKT | Tushare 日线/daily_basic |
| TS-DISC | Tushare disclosure_date |
| TS-ANN | Tushare 全量公告 anns_d（暂无权限） |
| CNINFO | 巨潮 |
| EXCH | 上交所/深交所 |

---

## 十、性能与延迟目标

| 场景 | 目标 |
|---|---:|
| 自定义股票池（≤ 300 只）筛选 | 95p ≤ 8s（不含 AI 冷启动） |
| 美股 1,500 只全池筛选 | 95p ≤ 30s |
| A 股 5,500 只全池筛选 | 95p ≤ 60s |
| 单股详情页（缓存命中） | ≤ 2s |
| 单股详情页（需调用 AI） | 95p ≤ 20s |
| 夜间全量刷新 | ≤ 120 分钟 |
| AI 单股风险分析 | 95p ≤ 12s；超时 20s 自动降级 |

### 降级策略

- AI 超时：展示规则结果 + `AI_PENDING`
- 数据源限流：切换备用源；仍失败则标 `SOURCE_DELAYED`
- 财报缺字段：尽量走 fallback 公式；关键字段缺失则标 `INSUFFICIENT_DATA`
- 点时文档未拉到：仍允许规则层运行，但 AI 风险状态强制 `REVIEW`

---

## 十一、日志与可追溯性（强制要求）

每个核心结果字段必须能追溯到：
- 证券 ID
- 期间 `period_end`
- `effective_date` / `accepted_date` / `ann_date`
- 源系统
- 源字段名
- 原始值
- 归一化值
- 公式版本
- 任务版本
- 运行 ID

### 最小日志结构

| 日志类型 | 必填字段 |
|---|---|
| 字段来源日志 | `run_id, ticker, field_name, source_code, source_record_key, period_end, effective_date, raw_value, normalized_value` |
| 公式日志 | `run_id, ticker, metric_name, formula_version, input_fields, output_value` |
| AI 日志 | `run_id, ticker, model_name, prompt_hash, input_doc_ids, output_json, latency_ms` |
| 错误日志 | `run_id, ticker, error_code, source_code, retry_count, final_action` |

---

## 十二、回测框架（点时严格）

- **市场**：美股、A 股分别独立回测
- **频率**：月度再平衡（P0），季度对比
- **持仓构建**：候选池 = HighConviction + NearFairPrice，等权
- **买入价格**：信号生效后下一交易日开盘价
- **卖出规则**：跌破质量门槛 / 触发硬 REJECT / 用户自定义最大持有期
- **对照组**：旧 30 因子模型 / 仅 ROCE 质量门槛 / Q+R / Q+R+V
- **基准指数**：美股 S&P 500，A 股 沪深 300

### 评估指标

| 指标 | 用途 |
|---|---|
| CAGR | 总效果 |
| Sharpe / Sortino | 风险调整收益 |
| Max Drawdown | 生存性 |
| Hit Rate | 体验指标 |
| Turnover | 与书中低频风格一致性 |
| Bucket Spread | 通过组 - 排除组的未来收益差（核心验证） |
| Expensive Penalty Spread | 便宜组 - 太贵组的未来收益差 |
| Governance Risk Spread | 高治理风险组 - 低风险组的未来收益差 |
| Coverage | 有效样本覆盖率 |

---

## 十三、AI Provider 配置

### 双 Provider 架构

| Provider | 默认模型 | SDK | 触发方式 |
|---|---|---|---|
| ChatGPT | `gpt-5`（chatgpt 5.4） | `openai>=1.30` | 用户绑定 OpenAI key |
| MiniMax | `abab-2.7-chat-completion-v2` | httpx 直连 | 用户绑定 group_id + key |

### Key 管理

- 每用户独立绑定 key（账户设置页输入）
- Fernet 加密存于 `user.{chatgpt|minimax}_api_key_encrypted`
- 加密密钥来自环境变量 `DARWEN_FERNET_KEY`（项目部署时生成，不入 git）
- 用户可设置 `ai_provider_default` 指定默认 provider
- 单次筛选任务可临时覆盖 provider 选择

### 失败回退

- ChatGPT 超时 → 自动尝试 MiniMax（如已绑定）
- 两个都失败 → 降级为 RULE_ONLY，screen_result.r_action 标 `RULE_ONLY`

---

## 十四、一句话目标

> **先用长期 ROCE 找到值得研究的公司，再用规则+AI 风险过滤排掉不该碰的公司，最后只在价格合适时给出研究/买入候选。所有结论可点时回溯、可解释、可覆核。**

---

*版本：2.0 | 生效：2026-05-09 | 维护：Darwin Engineering*
