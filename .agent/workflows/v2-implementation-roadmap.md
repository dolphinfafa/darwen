# V2 三层漏斗系统实施路线图

本文档定义 Darwen V2 重构剩余里程碑（M2-M7）的执行顺序、关键依赖与验收标准。

**当前状态**：M1 数据基础已完成（`milestones/2026-05-09.md`），M2-M7 待实施。

---

## 关键路径依赖

```
M1 数据基础 ✅
    ↓
M2 指标预计算（ROCE/CFO_NI/NetDebt等） ← 关键路径
    ↓
M3 三层漏斗引擎（Q/R/V Layer） ← 关键路径
    ↓
M4 AI 风险层（ChatGPT + MiniMax） ← 关键路径
    ↓
M5 API 层重写（V2 endpoints + Key 加密） ← 关键路径
    ↓
M6 前端重构（6 个新页面）
    ↓
M7 回测 + 端到端验证

非关键路径（可并行）：
M1.9 SEC filing 文本增强
M1.10 Polygon News 接入
```

---

## M2：指标预计算引擎（12 人日）

### 目标

实现 ROCE 严格公式 + 风险/价格层依赖的所有指标，预计算落库到 `metric_periodic`。

### 文件结构

```
backend/metrics/
├── __init__.py
├── compute.py          # 调度入口：compute_all_metrics(company_id, period_end)
├── helpers.py          # 复用 fact 表查询 + 多概念 fallback
├── roce.py             # ROCE 严格公式 + 5Y/10Y 序列
├── leverage.py         # interest_coverage, net_debt/EBIT, current_ratio
├── cash_quality.py     # CFO/NI, FCF, FCF<0 的年数
├── dilution.py         # share_count_cagr_5y
└── valuation.py        # pe_ttm（用 market_bar.close × shares × net_income TTM）
```

### 接口约定

```python
def compute_roce(db: Session, company_id: str, period_end: date,
                 formula_version: str = "v1") -> tuple[float | None, list[str], dict]:
    """返回 (value, source_fact_ids, lineage_dict)"""

def compute_all_metrics(db: Session, company_id: str, asof_date: date) -> list[MetricPeriodic]:
    """对单股全量重算所有指标，写入 metric_periodic + metric_lineage_log"""
```

### 关键实现细节

**ROCE 分母**：
- `OperatingCurrentAssets = current_assets - cash_and_equivalents - short_term_investments`（缺失 short_term_investments 时打 `EXCESS_CASH_PROXY_LOW_CONFIDENCE`）
- `OperatingCurrentLiabilities = current_liabilities - short_term_debt - current_portion_ltd - current_lease_liability`
- `NetFixedAssets = ppe_net`（**不计入** goodwill / intangibles / 长期股权投资）
- `CapitalEmployed = OCA - OCL + NetPPE`；若 ≤ 0 标 `NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED`

**ROCE 分子**（按市场分别处理）：
- US：优先 `account_code='OperatingIncomeLoss'`；fallback 到 `EBIT`
- CN：优先 canonical `operating_income`；fallback 到 `total_profit + interest_expense`

**5Y/10Y 序列**：
- 输入：`asof_date`
- 取 `period_end` 在 `[asof_date - 5y, asof_date]` 内的财年（必须满足 `accepted_date <= asof_date`，点时严格）
- 输出：`{2020: 0.275, 2021: 0.288, ..., 2024: 0.291}`

### 验收标准

```bash
# 1. ROCE 单股验证
python -c "
from backend.database import SessionLocal
from backend.metrics.roce import compute_roce_series
from datetime import date
db = SessionLocal()
series = compute_roce_series(db, 'CN_600519', date(2024, 12, 31), years=5)
print(series)
# 预期: 茅台 5Y ROCE 应 >= 30% 中位数
"

# 2. 全量回填
python -m backend.metrics.compute --all --asof 2024-12-31
# 预期: 548 + 10 公司各 7-8 个指标，约 4000+ 行写入 metric_periodic

# 3. 血缘日志
mysql -e "SELECT COUNT(*) FROM metric_lineage_log;"
# 预期: > 30,000 行（每个 metric 5+ source_fact_ids）
```

---

## M3：三层漏斗筛选引擎（18 人日）

### 文件结构

```
backend/screening/
├── __init__.py
├── funnel.py           # 顶层调度 funnel.run()
├── q_layer.py          # Q0-Q6 质量层
├── r_layer.py          # R1-R12 风险层（硬规则 + AI 调用）
├── v_layer.py          # V1-V5 价格层
├── exclusion.py        # 非适用证券判定
├── status_resolver.py  # 五状态裁决
└── reason_codes.py     # 原因码常量
```

### 核心接口

```python
def run(
    db: Session,
    universe: list[str],          # company_ids
    config: ScreenConfig,         # ROCE 门槛、风控敏感度、估值模式
    as_of_date: date,
    user_id: int,
    run_id: int = None,
) -> ScreenRun:
    """
    输出：每只股票 1 行 screen_result，含 status + reason_codes + metrics_snapshot
    """
```

### Q-Layer 实现

```python
def evaluate_q_layer(db, company_id, as_of_date, config) -> dict:
    company = db.get(Company, company_id)
    # Q0
    if company.instrument_type in ["BANK", "INSURANCE", "REIT", "ETF", "SPAC", ...]:
        return {"q_passed": False, "reason_codes": ["Q0_INSTRUMENT_TYPE"]}
    if company.is_excluded:
        return {"q_passed": False, "reason_codes": ["Q0_EXCLUDED"]}
    # Q6
    if company.list_date and (as_of_date - company.list_date).days < 5*365:
        return {"q_passed": False, "reason_codes": ["Q6_LIST_DATE_TOO_RECENT"]}
    # Q1: 财报年数
    fiscal_years = get_distinct_fiscal_years(db, company_id, as_of_date, max_back=10)
    if len(fiscal_years) < 5:
        return {"q_passed": False, "reason_codes": ["Q1_INSUFFICIENT_HISTORY"]}
    # Q2 + Q3
    roce_5y = read_metric_series(db, company_id, "roce", as_of_date, years=5)
    median = statistics.median(roce_5y.values())
    above_20 = sum(1 for v in roce_5y.values() if v >= 0.20)
    if median < 0.20 or above_20 < 4:
        return {"q_passed": False, "reason_codes": ["Q3_FAIL"], "roce_5y_median": median}
    # Q4
    roce_10y = read_metric_series(db, company_id, "roce", as_of_date, years=10)
    strong_track = (
        len(roce_10y) >= 8 and statistics.median(roce_10y.values()) >= 0.20
    )
    return {
        "q_passed": True,
        "q_strong_track": strong_track,
        "reason_codes": ["Q3_PASS"] + (["Q4_STRONG"] if strong_track else []),
        "roce_5y_median": median,
        "roce_10y_median": statistics.median(roce_10y.values()) if roce_10y else None,
    }
```

### R-Layer 实现要点

- 先跑 R1-R6 硬规则
- 任一硬规则 REJECT → 跳过 AI（节省成本）
- 否则调 AI orchestrator（参见 `ai-risk-layer.md`）
- AI 失败 → r_action = `RULE_ONLY`

### V-Layer 实现要点

- `pe_ttm` 来自 `metric_periodic` 或 fallback 现算
- 严格模式：`PE ≤ 14.9` → Acceptable
- 标准模式分级：strong_track → 22；passed → 18；其他 → 15
- EPS ≤ 0：直接标 `V_EPS_NEGATIVE`，进入 `Review`

### 验收标准

```bash
python -m backend.screening.funnel \
  --universe us_default \
  --as-of 2024-12-31 \
  --user-id 1 \
  --config-mode default
# 预期：548 美股中 HighConviction ≤ 5 家（应包含 Fastenal）
```

---

## M4：AI 风险层（14 人日）

### 文件结构

```
backend/ai/
├── __init__.py
├── provider_base.py        # AIProvider abstract
├── chatgpt_provider.py     # OpenAI SDK
├── minimax_provider.py     # httpx 直连 MiniMax
├── prompts/
│   ├── __init__.py
│   ├── version.py          # PROMPT_VERSION
│   └── risk_filter.py      # 系统 + 用户 prompt 模板
├── schema.py               # Pydantic 模型校验 AI 输出
├── crypto.py               # Fernet 加密 user 表 key
└── orchestrator.py         # 编排
```

### crypto.py 关键约束

```python
from cryptography.fernet import Fernet

def get_fernet() -> Fernet:
    key = os.getenv("DARWEN_FERNET_KEY") or get_settings().darwen_fernet_key
    if not key:
        raise RuntimeError("DARWEN_FERNET_KEY 未配置")
    return Fernet(key.encode())

def encrypt_api_key(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_api_key(ciphertext: str) -> str:
    return get_fernet().decrypt(ciphertext.encode()).decode()
```

部署前需生成 key 并写入 `.env`：
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 输出 e.g. "k4fHd8...=" 写入 .env: DARWEN_FERNET_KEY=k4fHd8...=
```

### orchestrator.py 流程

```python
def analyze_risk(
    db: Session,
    user_id: int,
    company_id: str,
    asof_date: date,
    rule_triggered_labels: list[str],
    provider_override: str = None,
) -> RiskAIResult:
    """
    1. 取 user 的 ai_provider_default + 解密对应 key
    2. 取 company 的财务摘要（last 5Y ROCE/CFO/NI/...）
    3. 取 company 的 text_document（最近 10 份按 published_at desc）
    4. 构造 prompt（PROMPT_VERSION + 业务上下文）
    5. 调 provider.chat()，超时 20s
    6. JSON schema 校验，失败重试 1 次
    7. 校验"AI 仅看法定披露才能给 REJECT"约束
    8. 写 risk_ai_result 表（含 prompt_hash、latency_ms）
    9. 返回 RiskAIResult ORM
    """
```

### Prompt 版本管理

```python
# backend/ai/prompts/version.py
PROMPT_VERSION = "v2026.05.09.001"
```

任何 prompt 变更必须 bump 版本，旧 prompt_version 的 risk_ai_result 自动作废（funnel 重跑）。

### 验收

```bash
# 1. 加密往返
python -c "
from backend.ai.crypto import encrypt_api_key, decrypt_api_key
plain = 'sk-test123'
enc = encrypt_api_key(plain)
print('encrypted:', enc[:30] + '...')
print('decrypted:', decrypt_api_key(enc))
"

# 2. ChatGPT provider mock 测试
python -m pytest backend/ai/tests/ -v

# 3. 实际调用（需真实 key）
python -c "
import os
os.environ['OPENAI_API_KEY'] = 'sk-...'
from backend.ai.orchestrator import analyze_risk_standalone
result = analyze_risk_standalone('US_AAPL', '2024-12-31')
print(result.overall_action, result.summary_cn)
"
```

---

## M5：API 层重写（10 人日）

### 新增 endpoints

```
POST   /v2/universe                          创建股票池
GET    /v2/universes                         我的股票池列表
POST   /v2/screen-config                     创建门槛配置
POST   /v2/screen-run                        发起异步筛选 → run_id
GET    /v2/screen-run/{run_id}               状态
GET    /v2/screen-run/{run_id}/results       结果分页
GET    /v2/screen-run/{run_id}/result/{cid}  单股详情
POST   /v2/backtest                          点时回测
GET    /v2/backtest/{id}/results             回测结果

POST   /v1/user/api-key                      绑定 ChatGPT/MiniMax key
GET    /v1/user/api-key/status               是否已绑定（不返回明文）
DELETE /v1/user/api-key
PATCH  /v1/user/ai-provider-default          切换默认 provider
```

### 异步任务

- `POST /v2/screen-run` 立即返回 run_id，BackgroundTasks 跑筛选
- `GET /v2/screen-run/{run_id}` 轮询查 status
- 大型筛选（≥ 500 只）建议接入 Celery（P1）

### main.py 路由注册

```python
from backend.api.screening import router as screening_router
from backend.api.backtest import router as backtest_router
from backend.api.user_settings import router as user_settings_router

app.include_router(screening_router)
app.include_router(backtest_router)
app.include_router(user_settings_router)
```

---

## M6：前端重构（14 人日）

### 6 个新页面

| 页面 | 路由 | 主要交互 |
|---|---|---|
| `UniverseConfig.vue` | `/universe` | 4 种来源（市场默认/指数/CSV/手工）→ 创建 universe |
| `ScreenConfig.vue` | `/screen-config` | ROCE 门槛、风控敏感度、估值模式表单 |
| `ScreenRun.vue` | `/screen-run/:runId` | 进度条 + 状态轮询，完成后跳转结果页 |
| `ScreenResults.vue` | `/screen-results/:runId` | 5 状态分桶展示，每桶可展开/排序 |
| `CompanyDetailV2.vue` | `/company/:companyId/run/:runId` | PRD 第 6 节模板（5 模块 + 证据抽屉） |
| `AccountSettings.vue` | `/account` | 绑定 ChatGPT/MiniMax key（前端加密提交，不存明文） |

### 删除旧页面

```
frontend/src/views/Screener.vue           ❌
frontend/src/views/CompanyDetail.vue      ❌
frontend/src/views/BatchReport.vue        ❌
frontend/src/views/BacktestV2.vue         ❌
```

### 复用

- `Login.vue`、`Admin.vue`、`App.vue` 框架、`style.css`、axios 拦截器
- Login 与 Admin 完全保留

### CompanyDetailV2 模块（PRD 第 6 节）

1. 结论摘要：5 状态徽章 + 建议动作
2. 核心指标：5Y/10Y ROCE 表 + 折线图 + 20% 阈值线
3. 风险标签：severity badges + evidence_doc_ids
4. 证据抽屉：点击 doc_id 弹层显示原文链接
5. 可视化：ROCE 折线 / PE vs 10Y 中位数 / CFO vs NI 柱图 / 股本变化

---

## M7：回测 + 端到端验证（8 人日）

### 文件

```
backend/backtest/
├── __init__.py
├── v2_engine.py        # 月度再平衡，按 accepted_date 严格点时
└── metrics_eval.py     # CAGR/Sharpe/MDD/Bucket Spread
```

### 实验范围（PRD 第 8 节）

- E1：vs 旧 30 因子模型（已删除，可对比 pre-v2-refactor tag 的回测结果）
- E2：质量门槛单调性（仅 Q-Layer）
- E6：点时偏差校验（filing/ann_date 回放 vs 静态年报）

### 端到端验证清单

1. 启动后端 `uvicorn backend.main:app --port 15001`
2. 启动前端 `npx vite --port 15002`
3. 浏览器登录 → 账户设置绑定 ChatGPT key
4. 新建股票池（默认美股池）
5. 用默认门槛运行筛选，等待完成（< 30s）
6. 看结果页 5 状态分布
7. 点击 Fastenal 进入单股详情，确认：
   - ROCE 5Y 中位数 ≥ 20%
   - 风险层 PASS
   - PE 状态显示 TooExpensive 或 NearFairPrice
   - 证据抽屉能看到 SEC filing 链接
8. 跑一次 2020-01 至 2024-12 月度回测，对照 S&P 500
9. 用 chrome-devtools-mcp 截图

---

## 中断与恢复

每次会话开始时按下列顺序恢复：

1. `git status` + `git log -5` 看进度
2. 读 `milestones/<latest>.md`
3. 读本文档定位下一里程碑
4. 看 TaskList 看任务状态
5. 用 `mysql ... SHOW TABLES` 确认 schema
