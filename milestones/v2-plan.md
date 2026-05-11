# Darwen V2 实施规划（M2-M7）

> 起稿：2026-05-11
> 基线：M1 数据基础已完成（commit 0576dd5）
> 总工作量：约 75 人日
> 关键路径：M2 → M3 → M4 → M5 → M6 → M7（M1.9 / M1.10 可暂缓）

---

## 0. 总览与依赖图

```
M2 (指标预计算) ──┐
                  ├──→ M3 (三层漏斗) ──→ M4 (AI 风险层) ──→ M5 (API) ──→ M6 (前端) ──→ M7 (回测/E2E)
M1.9 (SEC 文本) ──┤                       ↑
M1.10 (PG News)  ──┘  (M4 才会消费)
```

**并行机会**：M1.9 + M1.10 可与 M2 并行（不同模块、互不依赖）。M6 前端可在 M5 API 契约确定后启动 mock 阶段。

---

## 1. M2 指标预计算引擎（12 人日）

### 1.1 目录结构

```
backend/metrics/
├── __init__.py
├── helpers.py         # get_fact_value / get_fact_series / 字段映射
├── field_map.py       # SEC us-gaap account_code ↔ canonical name ↔ Tushare 字段
├── roce.py            # PRD 第 4 节严格口径
├── leverage.py        # net_debt / interest_coverage / current_ratio
├── cash_quality.py    # CFO/NetIncome, FCF, FCF<0 年数
├── dilution.py        # share_count_cagr (5Y)
├── valuation.py       # pe_ttm, ev_ebit
└── compute.py         # 调度入口 + 全量回填 runner
```

### 1.2 字段映射表（M2.1 核心交付物）

| canonical 名 | SEC account_code | Tushare 字段 | 用途 |
|---|---|---|---|
| revenue | Revenues / SalesRevenueNet / RevenueFromContractWithCustomerExcludingAssessedTax | income.revenue / total_revenue | 营收 |
| operating_income | OperatingIncomeLoss | income.operate_profit | EBIT 主源 |
| net_income | NetIncomeLoss | income.n_income_attr_p | 利润 |
| interest_expense | InterestExpense / InterestExpenseDebt | income.fin_exp_int_exp | 利息费用 |
| cfo | NetCashProvidedByUsedInOperatingActivities | cashflow.n_cashflow_act | 经营现金流 |
| capex | PaymentsToAcquirePropertyPlantAndEquipment | cashflow.c_pay_acq_const_fiolta | 资本开支 |
| current_assets | AssetsCurrent | balancesheet.total_cur_assets | 流动资产 |
| current_liabilities | LiabilitiesCurrent | balancesheet.total_cur_liab | 流动负债 |
| cash | CashAndCashEquivalentsAtCarryingValue | balancesheet.money_cap | 现金 |
| short_term_investments | ShortTermInvestments / MarketableSecuritiesCurrent | balancesheet.trad_asset | 短投 |
| short_term_debt | ShortTermBorrowings / CommercialPaper | balancesheet.st_borr | 短期借款 |
| current_portion_long_term_debt | LongTermDebtCurrent | balancesheet.non_cur_liab_due_1y | 一年内到期长债 |
| current_lease_liability | OperatingLeaseLiabilityCurrent | （A 股新租赁准则未必拆分，缺则置 0） | 一年内租赁负债 |
| long_term_debt | LongTermDebtNoncurrent | balancesheet.lt_borr | 长期借款 |
| net_ppe | PropertyPlantAndEquipmentNet | balancesheet.fix_assets | 固定资产净值 |
| common_shares_outstanding | CommonStockSharesOutstanding / WeightedAverageNumberOfSharesOutstandingBasic | balancesheet.total_share | 流通股数 |
| total_assets | Assets | balancesheet.total_assets | 总资产 |

> SEC 多个候选 tag 时按列表先后顺序回退。Tushare 字段以付费套餐字段名为准。

### 1.3 ROCE 严格口径（M2.2）

```python
ebit_t = get_fact("operating_income", period_end)
   # fallback A 股: operate_profit + fin_exp_int_exp
   # fallback 终极: total_profit + fin_exp_int_exp

operating_current_assets_t = current_assets - cash - short_term_investments
   # short_term_investments 缺失 → 置 0，notes += "EXCESS_CASH_PROXY_LOW_CONFIDENCE"

operating_current_liab_t = current_liabilities - short_term_debt - current_portion_long_term_debt - current_lease_liability
   # 任一缺失 → 置 0

capital_employed_t = (operating_current_assets_t - operating_current_liab_t) + net_ppe
   # 若 ≤ 0 → notes += "NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED"，roce 仍计算（不排除）

roce_t = ebit_t / capital_employed_t
```

**5Y 通过门槛**：`roce_5y_median ≥ 0.20` AND `count(roce_year ≥ 0.20) ≥ 4`
**10Y 强通过**：`count(10Y 可得) ≥ 8` AND `roce_10y_median ≥ 0.20` → 标签 `STRONG_TRACK_RECORD`

### 1.4 写库规约

每个指标按 `(company_id, period_end, metric_name, formula_version='v1')` 唯一写入 `metric_periodic`：

| metric_name | 类型 | 备注 |
|---|---|---|
| roce | 年度 | 当年值 |
| roce_5y_median | 截面（period_end=as_of） | 滚动中位数 |
| roce_10y_median | 截面 | 强通过标签判定 |
| ebit | 年度 | |
| capital_employed | 年度 | |
| fcf | 年度 | |
| cfo_ni_ratio | 年度 | |
| cfo_ni_5y_below_07_years | 截面 | R2 触发判定 |
| net_debt | 年度 | |
| net_debt_ebit | 年度 | R1 触发判定 |
| interest_coverage | 年度 | R1 触发判定 |
| current_ratio | 年度 | R1 触发判定 |
| share_count_cagr_5y | 截面 | R3 触发判定 |
| pe_ttm | 截面 | V 层主指标 |
| ev_ebit | 截面 | V 层备用 |

**血缘日志**：每个 metric 写完同步插入 `metric_lineage_log`，记录 `source_fact_ids`（list of fact_id） + `formula_version`。

### 1.5 验收

- 抽样手算 **MSFT 2023 ROCE** 对照引擎输出，偏差 < 1%
- 抽样手算 **贵州茅台 2023 ROCE**，偏差 < 1%
- `SELECT metric_name, COUNT(*) FROM metric_periodic GROUP BY metric_name` 每个 metric ≥ 4500 行（548 美股 × 10 年）
- `metric_lineage_log` 与 `metric_periodic` 行数 1:1（或 1:N，每个 fact_id 单独一行）

---

## 2. M3 三层漏斗筛选引擎（18 人日）

### 2.1 目录结构

```
backend/screening/
├── __init__.py
├── funnel.py          # run(universe, config, as_of_date, run_id, user_id)
├── exclusion.py       # Q0: instrument_type ∈ {BANK,INSURANCE,BROKER,REIT,ETF,SPAC,...} 排除
├── q_layer.py         # Q1-Q6
├── r_layer.py         # R1-R12（M3 阶段 AI 占位返回 PASS）
├── v_layer.py         # V1-V5
├── status_resolver.py # 五状态裁决逻辑
├── reason_codes.py    # 常量定义：Q3_FAIL, R1_LEVERAGE, V2_PASS, ...
└── config.py          # 阈值默认值（严格/标准/宽松模式）
```

### 2.2 reason_codes 命名约定

```
Q0_EXCLUDED_BANK, Q0_EXCLUDED_REIT, Q0_EXCLUDED_SPAC, ...
Q1_INSUFFICIENT_HISTORY (< 5 财年)
Q3_FAIL_5Y_ROCE, Q3_PASS
Q4_STRONG_TRACK_RECORD
Q5_NEGATIVE_CAPITAL_EMPLOYED
Q6_NEW_LISTING

R1_HIGH_LEVERAGE, R1_LOW_COVERAGE, R1_DETERIORATING_LIQUIDITY
R2_POOR_CFO_NI, R2_PERSISTENT_FCF_NEGATIVE
R3_HIGH_DILUTION
R4_SERIAL_ACQUIRER
R5_AUDIT_ISSUE (P1, 需 AI)
R6_REGULATORY_ACTION (P1, 需 AI)
R7_CUSTOMER_CONCENTRATION (P1)
R8_SUPPLIER_CONCENTRATION (P1)
R9_TURNAROUND_TRAP
R10_MANAGEMENT_INSTABILITY (P1)
R11_MINORITY_UNFRIENDLY (P1)
R12_DISRUPTION (P1)

V1_NEGATIVE_EPS
V2_PASS_STRICT (PE≤14.9)
V3_PASS_STANDARD (PE 14.9-18/22, 视等级)
V_TOO_EXPENSIVE
```

### 2.3 五状态裁决

```python
def resolve_status(q, r, v):
    if not q.passed:           return "Rejected"
    if r.action == "REJECT":   return "Rejected"
    if r.action == "REVIEW":   return "Review"
    if v.state == "TooExpensive": return "TooExpensive"
    # 价格通过
    if q.strong_track and r.action == "PASS" and v.state == "Cheap":
        return "HighConviction"
    return "NearFairPrice"
```

### 2.4 接口契约

```python
def run(universe: list[str], config: dict, as_of_date: date, run_id: int, user_id: int) -> None:
    """逐股运行漏斗，结果写入 screen_result。
    config 示例：
      {"roce_threshold": 0.20, "risk_sensitivity": "standard",
       "valuation_mode": "strict",  # strict|standard|loose
       "ai_provider": "chatgpt"}
    """
```

### 2.5 验收

- 10 家 A 股 + 50 家美股样本跑通，5 状态分桶非全 0
- screen_result.reason_codes 每行非空
- screen_result.metrics_snapshot 包含 roce_5y_median / pe_ttm / net_debt_ebit 等关键字段

---

## 3. M4 AI 风险层（14 人日）

### 3.1 目录结构

```
backend/ai/
├── __init__.py
├── crypto.py              # Fernet encrypt/decrypt，密钥来自 DARWEN_FERNET_KEY
├── provider_base.py       # AIProvider 抽象基类（call(prompt, docs) -> dict）
├── chatgpt_provider.py    # OpenAI SDK，model=gpt-5
├── minimax_provider.py    # httpx 直连，model=abab-2.7
├── schema.py              # Pydantic 输出校验
├── prompts/
│   ├── __init__.py
│   ├── version.py         # PROMPT_VERSION = "v1"
│   └── risk_filter.py     # PRD 第 4.5 节模板
└── orchestrator.py        # 编排：取 user key → 选 provider → 调用 → 校验 → 落库
```

### 3.2 Fernet 加密

- 启动时读 `os.environ["DARWEN_FERNET_KEY"]`（base64）
- 部署脚本：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` → 写入 `.env`（不入 git）
- 加密函数：`encrypt(plaintext) → base64`，解密时若 key 失配抛 `InvalidToken`

### 3.3 Provider 接口

```python
class AIProvider(ABC):
    @abstractmethod
    async def call(self, system_prompt: str, user_prompt: str, *, timeout: float = 20.0) -> dict:
        """返回解析后的 dict；非 JSON 抛 InvalidResponseError"""
```

### 3.4 调用流程（orchestrator）

```python
async def analyze_risk(company_id, as_of_date, docs, run_id, user) -> RiskAIResult:
    provider = pick_provider(user)  # 用户默认 or 任务覆盖
    prompt = build_prompt(company, docs, structured_signals)
    prompt_hash = sha256(prompt)

    for attempt in range(2):  # 1 次重试
        try:
            t0 = time.monotonic()
            raw = await provider.call(SYSTEM_PROMPT, prompt, timeout=20)
            latency = int((time.monotonic() - t0) * 1000)
            validated = RiskAIOutput.model_validate(raw)
            return persist(validated, raw, prompt_hash, latency, run_id, ...)
        except InvalidResponseError:
            continue
        except (TimeoutError, APIError) as e:
            return downgrade_to_rule_only(reason=str(e))

    # 两次都失败
    return downgrade_to_rule_only(reason="invalid_json_after_retry")
```

### 3.5 融合规则（接回 R 层）

```python
def fuse_r_layer(rule_result, ai_result):
    # REJECT 仅当：AI 高置信(≥0.8) 且 证据为法定披露 或 硬规则同向触发
    if ai_result.overall_action == "REJECT":
        if any(label.confidence >= 0.8 and is_regulatory(label.evidence_doc_ids)
               for label in ai_result.labels):
            return "REJECT"
        if rule_result.hard_triggered:
            return "REJECT"
        return "REVIEW"  # 降级
    if ai_result.overall_action == "REVIEW" or rule_result.soft_triggered:
        return "REVIEW"
    return "PASS"
```

### 3.6 验收

- 1 家美股 + 1 家 A 股端到端调用（需用户绑定 key 或测试 key）
- risk_ai_result 表落数据，含 prompt_hash / latency_ms
- 模拟超时：返回 RULE_ONLY，screen_result.r_action = "RULE_ONLY"
- 模拟非 JSON：重试 1 次后降级 RULE_ONLY

---

## 4. M5 API 层（10 人日）

### 4.1 endpoints

| Method | Path | 用途 |
|---|---|---|
| POST | /v2/universe | 创建股票池（市场/指数/CSV 上传/手工 ticker 列表） |
| GET | /v2/universe/{id} | 查询股票池 |
| POST | /v2/screen-run | 异步启动筛选，返回 run_id |
| GET | /v2/screen-run/{id} | 查询 run 状态（running/completed/failed） |
| GET | /v2/screen-run/{id}/results | 5 状态分桶列表（分页） |
| GET | /v2/screen-run/{id}/result/{company_id} | 单股详情（metrics + reason_codes + AI + 证据 doc_ids） |
| POST | /v2/backtest | 启动月度再平衡点时回测 |
| GET | /v2/backtest/{id} | 回测结果 |
| POST | /v1/user/api-key | 绑定 ChatGPT/MiniMax key（body 加密落库） |
| GET | /v1/user/api-key | 返回掩码（如 `sk-***x9q3`） |
| DELETE | /v1/user/api-key | 解绑 |

### 4.2 异步任务

- 用 FastAPI BackgroundTasks（小规模够用），或迁移到 RQ/Celery（M5 后续优化）
- screen_run.status 由 worker 写入；前端轮询 GET /v2/screen-run/{id}

### 4.3 Pydantic schemas

新建 `backend/schemas/v2.py`：UniverseCreate / ScreenRunCreate / ScreenResultDetail / RiskAIResultOut / MetricsSnapshot / ApiKeyBind。

### 4.4 验收

- OpenAPI /docs 全部 endpoints 可见 + 可调
- Postman/curl 跑通完整链路：创建 universe → 启动 screen → 轮询 → 看结果

---

## 5. M6 前端重构（14 人日）

### 5.1 删除旧页面

- `frontend/src/views/Screener.vue`
- `frontend/src/views/CompanyDetail.vue`
- `frontend/src/views/BatchReport.vue`
- `frontend/src/views/BacktestV2.vue`
- 清理 router 注册和导航菜单

### 5.2 新建 6 个页面

| 页面 | 关键交互 |
|---|---|
| UniverseConfig.vue | 标签页：市场（US/CN/Mixed）/ 指数（S&P500/沪深300）/ CSV 上传 / 手工 ticker 输入 |
| ScreenConfig.vue | 表单：ROCE 门槛（默认 20%）、风控敏感度（strict/standard/loose）、估值模式（strict/standard/loose）、AI provider（chatgpt/minimax） |
| ScreenRun.vue | 显示进度条 + 已完成/总数 + 轮询 status |
| ScreenResults.vue | 5 状态分桶 tab（Rejected / Review / TooExpensive / NearFairPrice / HighConviction），每行列出 ticker / 公司名 / roce_5y / pe_ttm / 主要 reason_codes |
| CompanyDetailV2.vue | 区块：基础信息 / Q 层结果 / R 层结果（AI 标签 + 证据抽屉） / V 层结果 / 字段血缘表 |
| AccountSettings.vue | ChatGPT key 输入 + MiniMax key + group_id 输入 + 默认 provider 选择 |

### 5.3 共享组件

- `<EvidenceDrawer>` — 点击 doc_id 弹出原文/链接
- `<ReasonCodeBadge>` — reason_code 中文化（如 R1_HIGH_LEVERAGE → "杠杆过高"）
- `<MetricLineageTable>` — 字段血缘展示

### 5.4 验收

- 端到端可用：登录 → 设 key → 建池 → 配置 → 跑 → 看结果 → 进详情 → 看证据
- 5 状态分桶切换正确
- AI 调用失败显示 RULE_ONLY 提示

---

## 6. M7 回测 + 端到端（8 人日）

### 6.1 backtest/v2_engine.py

- 月度再平衡（每月第一个交易日）
- 每个 rebalance date：按 accepted_date ≤ 当日 取 facts → 跑 funnel → 候选 = HighConviction + NearFairPrice → 等权
- 买入价 = 信号生效日次交易日开盘
- 卖出规则：跌破 Q3、触发硬 REJECT、超 max_holding（默认 36 个月）
- 输出：组合净值序列、CAGR、Sharpe、Max DD、Hit Rate、Turnover

### 6.2 PRD 第 8 节实验

| 编号 | 验证内容 | 方法 |
|---|---|---|
| E1 | V2 vs 旧 30 因子 | 同周期跑两套，比 CAGR/Sharpe |
| E2 | 质量门槛单调性 | 把 ROCE 门槛设 15/20/25/30%，看 forward return 是否单调 |
| E6 | 点时偏差校验 | 抽 10 个历史日期，确认筛选只用了 accepted_date ≤ 当日的 fact |

### 6.3 端到端 smoke

```
1. POST /v1/auth/login          # 已有用户
2. POST /v1/user/api-key        # 绑 key
3. POST /v2/universe            # 美股 S&P 500 / 10 家 A 股
4. POST /v2/screen-run          # 启动
5. 轮询 GET /v2/screen-run/{id} # 直到 completed
6. GET /v2/screen-run/{id}/results # 看 5 桶分布
7. GET /.../result/{company_id} # 进一家 HighConviction 详情
```

---

## 7. 关键约束清单（M2-M7 全程务必遵守）

| # | 约束 | 出处 |
|---|---|---|
| 1 | 点时严格：信号生效日 = accepted_date 次个交易日 | PRD 第 5/12 节 |
| 2 | 不输出综合总分，只输出 5 状态 + reason_codes | PRD 执行摘要 |
| 3 | AI 仅触发 REVIEW（原则上），REJECT 需高置信+法定披露 | PRD 第 6 节融合规则 |
| 4 | 每个字段可追溯 metric_lineage_log | PRD 第 11 节 |
| 5 | ROCE 严格按书中口径，剔除 cash/短投/商誉/无形 | PRD 第 4 节 |
| 6 | 银行/保险/券商/REIT/ETF/SPAC 默认排除 | PRD 第 5 节 Q0 |
| 7 | prompt_hash + 模型名 + temperature 全部入库 | PRD 第 11 节 |
| 8 | AI 输出非 JSON 自动重试 1 次，再失败 RULE_ONLY | PRD 第 10 节降级 |

---

## 8. 暂缓项（M1.9 / M1.10）

| 项 | 影响 | 何时做 |
|---|---|---|
| M1.9 SEC filing 文本与元数据 | M4 AI 风险层缺美股 10-K 全文证据 | M4 启动前补 |
| M1.10 Polygon News | M4 美股新闻入风险层 | M4 启动前补 |

> 二者均可与 M2 并行（独立模块），由用户决定何时切入。

---

## 9. 风险与未解决项

| 风险 | 应对 |
|---|---|
| Tushare `anns_d` 无权限 | A 股 AI 风险层证据缺失；P1 接巨潮（CNINFO）备源 |
| AKSHARE 旧数据与 TS-FS 共存 | M2.1 字段映射阶段优先 TS-FS，AKSHARE source 仅做 fallback；M2 完成后评估清理 |
| Fernet key 管理 | 必须在 .env 配置 DARWEN_FERNET_KEY，否则 user key 无法解密；部署文档需增 setup 步骤 |
| ChatGPT gpt-5 模型名 | 若 OpenAI 实际不存在该模型 ID，需在 M4 启动时确认并切换（如 gpt-4-turbo） |

---

## 10. 起步建议

**建议从 M2.1（字段映射 & helpers）开始**——它是 M2 全部子任务的前置依赖，且产出物（field_map 表 + helpers 函数）可立刻用 1-2 家公司验证字段口径是否对齐 SEC us-gaap & Tushare 实际字段名。一旦验证通过，M2.2-M2.4 可并行铺开。

---

*本规划由 Claude Agent 起草，请用户审阅后确认起步任务。*
