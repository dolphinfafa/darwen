# V2 三层漏斗系统实施路线图

本文档定义 Darwen V2 重构剩余里程碑（M2-M7）的执行顺序、关键依赖与验收标准。

**当前状态**：筛选为 **ROCE → 稳健性 → 风险性 三层全自动漏斗**（2026-06-20 起默认 auto_advance 连跑，
人工 gate 的 HTTP 层已移除）；底层 V2 工程闭环 + 数据修补（含 2025 财年）+ AI 调用沿用 2026-05-13 版本。

工作日志：
- `milestones/2026-05-12.md` — M1-M7 主线 + 全量回填 (12 章)
- `milestones/2026-05-13.md` — A 股 close / 金融股 / TSLA 财年 / E6 / 中文标签 / M4 真实 AI (12 章)
- `milestones/2026-06-18.md` — **三层漏斗重构**（ROCE 可配置 / 分层 gate / AI 双层 / 我的股票池 / 详情页瘦身，11 章）
- `milestones/2026-06-19.md` — AI 介入范围可选 + 漏斗两 bug 修复 + PRD V2.1
- `milestones/2026-06-20.md` — **漏斗改全自动**（取消人工 gate + 移除 /advance /manual）+ 筛选历史删除 + 详情页/原因标签 tooltip

### 2026-06-20 架构演进（现行筛选流程，优先于下方历史路线图）

筛选改为**全自动三层漏斗**：过 ROCE 自动进稳健性、过稳健性自动进风险性、通过风险性即最终入选，
取消每层人工暂停。

- `ScreenRunCreateRequest.auto_advance` 默认 `True`，前端 `UniverseConfig` 传 `auto_advance: true`；
  引擎 `funnel_v2.run_from` 在 `auto_advance` 下连跑 roce→sturdiness→risk→`_finalize` 定稿。
- **已移除人工 gate 的 HTTP 层**：`POST /v2/screen-run/{id}/advance`、`/manual` 端点 + schema
  `AdvanceResponse`/`ManualActionRequest` + 前端 `advanceLayer`/`manualAction`。`FunnelResults.vue`
  退化为纯展示（运行进度 → 三层漏斗 → 最终入选）。
- **保留**：引擎层 `finalize_run` / `run_from` 非 auto 分支（无 HTTP 入口的引擎能力）、
  `manual_action` 数据字段（详情展示是否人工干预过）。`auto_advance=False` 路径引擎仍在但无外部推进入口。
- 其余沿用下方 2026-06-18 架构（层语义 / AI / 存活集 / 迁移均不变）。

### 2026-06-20 后续：AI 风险层有效性修复

用户实测后两层（稳健/风险）不过滤任何股票，查出两层叠加根因并修复：
- **证据检索点时 bug**（`orchestrator._load_recent_documents`）：先 `LIMIT` 后 Python 点时过滤，
  as_of 早于公司最新文档时喂给 AI 的证据为 0 → 裸判 PASS。修复：点时过滤移入 SQL WHERE。
- **过滤标准**（`funnel_v2._eval_sturdiness`/`_eval_risk`）：改为 AI `REVIEW`/`REJECT` 出局、
  `PASS`/`MONITOR` 通过（此前仅 REJECT 出局，后两层几乎不过滤）。
- commit `6524b03` / `52fee38`，详见 `milestones/2026-06-20.md` 六节。

### 2026-06-20 TTM 口径评估 —— 决定暂不做（维持年报口径）

用户曾拟「纳入 2026 季报、ROCE 改 TTM（滚动 12 个月）」，经 plan mode 探索 + 数据核查后**决定
暂不实施**，维持年报口径。理由：① 季度 ROCE 噪声偏离 Pulak「长期一致性」本质；② TTM EBIT 需 4 季
求和，fact 表最新一条是 Q4 单季还是 FY 全年需逐家甄别、易算错；③ A 股季报口径差异。
`as_of=2025-12-31` 已是最新完整财年（非旧数据）。

- **FY2026 推进 SOP（约 2027 初年报齐备后）**：`compute.py` 的 `persist_all_metrics_*` 默认
  `year_range` 上限 2025→2026；`schemas/v2.py` 的 `as_of_date` 默认改 `date(2026,12,31)`；
  重跑 `persist_all_metrics_bulk`（548 美股约 12 分钟），无需改计算逻辑。
- 若将来仍想用季报：最轻量方案是往 `metric_periodic` 写一条 `period_end=2026-xx`/`roce` 的行，
  `q_layer._read_roce_series`（按 period_end.year 去重、现场算中位数）会自动纳入，无需动 q_layer。

### 2026-06-18 架构演进（层定义与实现细节，仍现行；推进方式已被上方全自动取代）

筛选流程已从 Q/R/V（质量/风险/估值）改为 **ROCE → 稳健性 → 风险性**：

```
选股票池(内嵌 ROCE 阈值 + 回溯年数 3/5/7/10)
  → ① ROCE 门槛(规则,按 N 年现算)
  → ② 稳健性(规则:无负债现金流 + AI:客户/供应商/行业/管理层)
  → ③ 风险性(AI:诚信/转型/并购/靠预测/利益相关者)
  → 入选
```

- 引擎 `screening/funnel_v2.py`：存活集 = `screen_result.rejected_at_layer IS NULL`；
  `auto_advance=True`（现默认）连跑 roce→sturdiness→risk→`_finalize` 定稿。
  〔2026-06-20 起人工 gate（`awaiting_review` + `/manual` + `/advance`）已移除，见上方 06-20 节〕
  `GET /v2/screen-run/{id}/funnel` 出漏斗数据。
- AI 走 `ai/orchestrator.analyze_layer(layer=sturdiness|risk)`，prompt 分 `prompts/sturdiness_filter`（4 类）
  / `prompts/risk_filter`（8 类）；`risk_ai_result.layer` 区分；融合规则保守（REJECT 需法定披露）。
- 新增"我的股票池"：`api/watchlist.py` + `models/watchlist.py` + `MyWatchlist.vue`。
- 前端：`FunnelResults.vue`（漏斗展示页，gate 已于 06-20 移除）替代 `ScreenResults` 角色；`UniverseConfig` 内嵌 ROCE 配置；
  `CompanyDetailV2` 瘦身为「历史 ROCE + 过滤原因 + 出处」+ 入池按钮；`MyRuns` 行内改名。
- 迁移：`funnel_v2_layers` / `add_risk_ai_layer` / `add_watchlist`（均加列/加表，可回滚）。
- **旧 Q/R/V**（`screening/funnel.py`/`v_layer.py`、`ScreenConfig.vue`、`ScreenResults.vue`）保留
  **deprecated** 未删除。下方 M2-M7 章节为**历史路线图**（旧架构），保留供追溯。

系统端到端**生产可用**：

- UI → API → 漏斗筛选 → AI 风险层 (apiyi gpt-4.1-mini 实跑) → Bucket Spread + 月度回测
- 美股估值精度齐：A 股 Tushare 不复权 + 金融股 dei.Entity 股本 + TSLA/NVDA SEC fye 权威
- 96% 美股有 AI 证据（485 SEC + 500 News），AI 实测 ~2.5s/家
- PRD E2 ROCE 单调性验证：10/20/30% CAGR 26.7%/28.9%/34.5%
- PRD E6 点时严格性：0 vs 120 天 lag 差 5.6%（接近 <5% 阈值）
- 前端 reason_code 中文化（51 项 + tooltip）

后续可选：月度回测前端可视化 / M7 v3 基准对比 / 行业中性化 / MiniMax 充值。

---

## 关键路径依赖

```
M1 数据基础 ✅
M1.x SEC 字段修补 ✅ (CORE_CONCEPTS 扩 7 个 tag，548 美股增量重拉)
    ↓
M2 指标预计算（5 模块全部完成）✅
   M2.1 字段映射 & helpers ✅
   M2.2 ROCE 严格口径 + 5Y/10Y 门槛 ✅
   M2.3 杠杆 (R1) + 现金质量 (R2) ✅
   M2.4 稀释 (R3) + 估值 (V Layer) ✅
   M2.5 调度器整合 + 全量回填 ✅
    ↓
M3 三层漏斗引擎（Q/R/V Layer + 5 状态裁决） ✅
   8 模块 / 548 家 3.6s / strict-standard-loose 单调 / HighConviction 4 家
    ↓
M4 AI 风险层（ChatGPT + MiniMax + Fernet 加密） ✅
   9 文件 / 重试 1 次 / fallback 双 provider / PRD 融合规则 / 端到端 4 路径过
    ↓
M5 API 层重写（V2 endpoints + Key 绑定） ✅
   4 文件 / 10 endpoint / OpenAPI /docs 可见 / 端到端 8/8 过
    ↓
M6 前端重构（6 个新页面） ✅
   删除 4 旧页面 / 新建 6 页 / vite 195ms 构建 / V2 路由
    ↓
M7 Bucket Spread 回测 + 端到端 ✅
   3 模块 + API / 端到端 6/6 / NearFairPrice 80% win rate 价值策略验证
    ↓
M7 v2 月度滚动回测 ✅
   2020-2024 美股 standard：CAGR 28.9% / Sharpe 1.24 / MaxDD -24%
   PRD E2 单调性：ROCE 10/15/20/25/30% CAGR 单调上升
    ↓
M1.9 SEC filing 文本 ✅
   8,440 text_document + 108,761 filing accepted_at；485/548 美股有 SEC 证据
    ↓
M1.10 Polygon News ✅
   14,632 新闻覆盖 500 家美股，含 publisher/tickers/keywords 元数据
    ↓
数据修补 A 股 close ✅
   Tushare daily_basic 不复权 + total_mv 替换 V1 akshare 复权价
   茅台 close 8863→1524 / mc 11T→1.91T / PE 143x→24.7x
    ↓
数据修补 金融股 shares + Q0 ✅
   SEC dei.EntityCommonStockSharesOutstanding 拉取 24,558 行 +
   _pick_common_security 选普通股排除优先股 +
   88 家美股按 SIC 重设 instrument_type (BANK 31/BROKER 26/INSURANCE 20/REIT 11)
   JPM mc 55B→658B / Goldman 11B→181B / MCD PE 0.00002x→23.8x
    ↓
数据修补 TSLA/NVDA 财年末 ✅
   company.fiscal_year_end_month 列 + Alembic 迁移 +
   SEC submissions.fiscalYearEnd 权威填充 543 美股 + 50 A 股
   TSLA fye 3→12 / NVDA fye 10→1
    ↓
E6 点时偏差校验 ✅
   pit_audit.py: lookback 0-180 天 CAGR 波动 <2pp
   美股年报中位披露 lag = 41 天 << 120 天 lookback
   PRD <5% 阈值几乎达标 (1.68 pp = 5.6%)
    ↓
reason_code 中文 label ✅
   后端 reason_labels.py 51 项映射 + 2 API +
   前端 ReasonPill 组件按 severity 着色 + layer 边框
    ↓
M4 真实 AI 调用 ✅
   ChatGPT 走 apiyi gpt-4.1-mini 端到端 8 步全过
   5 家公司 11.8s 含 4 次真实调用，AI 正确识别 Apple/NVDA/TSLA
   股权稀释 → AI_MINORITY_SHAREHOLDER_RISK → REVIEW

后续可选：
- 月度回测前端可视化页（净值曲线 + lookback 对比图）
- M7 v3 基准对比 (vs S&P 500) / 行业中性化 / 多空对冲
- MiniMax provider 端到端（待用户充值国内版账户）
```

---

## M2：指标预计算引擎（12 人日）

### 目标

实现 ROCE 严格公式 + 风险/价格层依赖的所有指标，预计算落库到 `metric_periodic`。

### 文件结构（实际落地）

```
backend/metrics/
├── __init__.py        ✅
├── field_map.py       ✅ 24 canonical → SEC us-gaap / TS-FS / AKSHARE 三向映射 + source 优先级链
├── helpers.py         ✅ get_fact_value / get_fact_value_asof (三轨可见性 + annual_only) /
│                         get_annual_periods (annual_only) / get_fiscal_year_end (NI-mode 推断)
├── roce.py            ✅ compute_roce_series + evaluate_quality_gate (PRD 第 4 节，Q5_RECENT_NEG_CAP)
├── leverage.py        ✅ compute_leverage_series（消费 ebit_by_year）
├── cash_quality.py    ✅ compute_cash_quality_series + evaluate_cash_quality_gate
├── dilution.py        ✅ compute_dilution_series + evaluate_dilution_gate（拆股检测）
├── valuation.py       ✅ compute_valuation_snapshot (market_cap / pe_ttm / ev_ebit)
└── compute.py         ✅ persist_all_metrics_for_company 调度 5 模块 + 共享 fact_meta_lookup
                          每模块独立 formula_version（roce_v1 / leverage_v1 / cash_quality_v1 / dilution_v1 / valuation_v1）
```

### M2.1/M2.2 已落地的关键决策

1. **fact.account_code 字段含义**：M1 重构时退化为字面 "us-gaap" / "cn-cas"，真实 tag 在 `concept` 字段。helpers 已按 source_type + concept 候选回退查询。
2. **跨 source 回退**：A 股 helpers 优先 TS-FS（10 家有数据），其余 40 家自动回退 AKSHARE。helpers 透传 source_type 给血缘日志。
3. **严格年报模式**：`get_annual_periods(annual_only=True)` 仅取 period_end.month == fiscal_year_end_month 的 fact，避免 Q1/Q3 季报混入年度序列。A 股一律 fy_end_month=12，美股按 Revenues period_end 月份众数推断。
4. **降级标签**：
   - `EXCESS_CASH_PROXY_LOW_CONFIDENCE` — short_term_investments 缺失置 0
   - `NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED` — capital_employed ≤ 0，roce=None，不自动排除
   - `EBIT_FROM_OP_INC_PLUS_INTEREST` / `EBIT_FROM_TOTAL_PROFIT_PLUS_INTEREST` — A 股 EBIT 回退路径
   - `EBIT_INTEREST_EXPENSE_MISSING_ZEROED` — A 股利息费用缺失
5. **质量门槛窗口**：取**最近 5 个完整财年**（含 invalid），近 5 年内 ≥ 2 年 NEGATIVE_CAP 走 Q5_RECENT_NEG_CAP_OR_MISSING 人工覆核，避免大现金/负 NWC 公司（Apple/Visa）用早期 valid 年补窗口。
6. **fact_id 与血缘**：RoceComponents.source_fact_ids 收集每个输入字段的 fact_id；compute.py 写血缘时批量查 fact → (source_type, raw_value, accepted_date)，每输入字段一行 metric_lineage_log。

### SEC 字段修补结果

CORE_CONCEPTS 新增 7 个 tag：
- ShortTermInvestments / MarketableSecuritiesCurrent — STI 主源 / Apple 类公司用 Marketable
- LongTermDebtCurrent — 一年内到期长债
- LongTermDebtNoncurrent — 非流动长期借款
- OperatingLeaseLiabilityCurrent / FinanceLeaseLiabilityCurrent — 一年内租赁负债
- CommercialPaper — 商业票据，Apple 类公司的"短期借款"

重拉 546 美股，新增约 2.3 万条 fact。Cisco ROCE 213% → 22%；Apple/Visa 由原"假阳通过"→ Q5 正确捕获。

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

### 验收命令（实测，含 5 模块）

```bash
# 1. 单股快速验证（含 5 模块）
/opt/miniconda3/envs/darwen/bin/python -c "
from datetime import date
from backend.database import SessionLocal
from backend.metrics.roce import compute_roce_series, evaluate_quality_gate
from backend.metrics.leverage import compute_leverage_series
from backend.metrics.cash_quality import compute_cash_quality_series, evaluate_cash_quality_gate
from backend.metrics.dilution import compute_dilution_series, evaluate_dilution_gate
from backend.metrics.valuation import compute_valuation_snapshot
db = SessionLocal()
cid = 'US_0000789019'  # MSFT
roce = compute_roce_series(db, cid, (2014, 2024))
ebit = {c.year: c.ebit for c in roce if c.ebit}
gate = evaluate_quality_gate(roce)
val = compute_valuation_snapshot(db, cid, date(2024, 12, 31))
print(f'MSFT roce_5y={gate.median_5y*100:.1f}% strong={gate.strong_track_record} pe_ttm={val.pe_ttm:.1f}x')
# 实测: MSFT roce_5y=29.7% strong=True pe_ttm=35.2x
"

# 2. 全量回填（5 模块）
mysql -h 127.0.0.1 -uroot -pdarwen_dev_123 darwen -e "TRUNCATE TABLE metric_periodic; TRUNCATE TABLE metric_lineage_log;"
/opt/miniconda3/envs/darwen/bin/python -m backend.metrics.compute
# 实测: 598/598 OK, year_rows=65887, section_rows=6793, lineage_rows=86811,
#       pass_5y_count=172, strong_count=146, 12 分钟

# 3. SEC 字段增量回填（CORE_CONCEPTS 变更后）
/opt/miniconda3/envs/darwen/bin/python -m backend.pipeline.sec_edgar.backfill_tags
# 实测: 548 美股、546 OK、2 errors，~4 分钟

# 4. fail_reason 分布巡检
mysql -h 127.0.0.1 -uroot -pdarwen_dev_123 darwen -e "
SELECT notes, COUNT(*) FROM metric_periodic WHERE metric_name='q3_pass_5y' GROUP BY notes ORDER BY 2 DESC;
"

# 5. 各 formula_version 行数分布
mysql -h 127.0.0.1 -uroot -pdarwen_dev_123 darwen -e "
SELECT formula_version, COUNT(DISTINCT metric_name) n_metrics, COUNT(*) cnt
FROM metric_periodic GROUP BY formula_version;
"
# 实测: roce_v1 (11 metrics, 33,699) leverage_v1 (4, 20,144) cash_quality_v1 (6, 12,530)
#       dilution_v1 (2, 3,979) valuation_v1 (4, 2,328)

# 6. V2 strict 模式候选（PE ≤ 14.9 + Q3 通过）
mysql -h 127.0.0.1 -uroot -pdarwen_dev_123 darwen -e "
SELECT c.market, c.name, ROUND(pe.value,1) pe, ROUND(m5.value*100,1) roce_5y
FROM metric_periodic pe
JOIN metric_periodic m5 ON pe.company_id=m5.company_id AND m5.metric_name='roce_5y_median'
JOIN metric_periodic q3 ON pe.company_id=q3.company_id AND q3.metric_name='q3_pass_5y' AND q3.value=1
JOIN company c ON pe.company_id=c.company_id
WHERE pe.metric_name='pe_ttm' AND pe.value BETWEEN 3 AND 14.9 AND m5.value > 0.20
ORDER BY pe.value LIMIT 15;
"
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

---

## 已落地的数据修补 SOP（2026-05-13）

### A 股 close 不复权

V1 时代 akshare 拉的 A 股是后复权 hfq 价（茅台 8863 vs 实际 1524）。
修复方案 C 双源：Tushare daily (不复权) + daily_basic.total_mv 落库 market_bar。

```bash
# 删除 50 家旧 market_bar 行 + 重拉 Tushare 不复权（2 分钟）
python -m backend.pipeline.cn_stock_v2.fix_close_unadjusted

# 重算 50 家 metric_periodic
python -c "
from backend.metrics.compute import persist_all_metrics_bulk
from backend.database import SessionLocal
from backend.models.company import Company
from sqlalchemy import select
db = SessionLocal()
ids = [r[0] for r in db.execute(select(Company.company_id).where(Company.market=='CN_A')).all()]
persist_all_metrics_bulk(company_ids=ids)
"
```

### 金融股 shares + Q0 (3 步)

1. SEC ingest 加 dei.EntityCommonStockSharesOutstanding（已合入 company_facts.CORE_CONCEPTS + DEI_CONCEPTS 双 taxonomy）
2. valuation._pick_common_security 选 ticker 不含 '-' / '.PR' 的普通股
3. SIC 重设 instrument_type：6020-6029→BANK / 62xx→BROKER / 63xx→INSURANCE / 6798→REIT

```bash
# 增量重拉 548 美股 (dei + 新 tag)
python -m backend.pipeline.sec_edgar.backfill_tags

# SIC 重设 instrument_type（一次性脚本，参考 milestones/2026-05-13.md 七节）
# 88 家美股从 COMMON 重分类
```

### TSLA/NVDA 财年末权威化

```bash
# Alembic 迁移加 company.fiscal_year_end_month
alembic upgrade head

# 从 SEC submissions.fiscalYearEnd 填充（2 分钟）
python -m backend.pipeline.sec_edgar.fill_fiscal_year_end
```

### 重算 metric_periodic

任何数据修补后都要重算指标：

```bash
# 548 美股 ~12 分钟
python -c "
from backend.metrics.compute import persist_all_metrics_bulk
from backend.database import SessionLocal
from backend.models.company import Company
from sqlalchemy import select
db = SessionLocal()
ids = [r[0] for r in db.execute(select(Company.company_id).where(Company.market=='US')).all()]
persist_all_metrics_bulk(company_ids=ids)
"
```

---

## AI 真实调用 SOP（2026-05-13）

### 配置 ChatGPT 代理

```ini
# .env
DARWEN_FERNET_KEY=...
DARWEN_CHATGPT_BASE_URL=https://api.apiyi.com/v1
DARWEN_CHATGPT_MODEL=gpt-4.1-mini
```

### 用户绑 key（推荐通过 API）

```bash
# 走 /v1/user/api-key POST
curl -X POST http://localhost:15001/v1/user/api-key \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"provider":"chatgpt","api_key":"sk-..."}'
```

### 启动 AI 风险层筛选

```bash
# 走 /v2/screen-run，enable_ai_risk_layer=true
curl -X POST http://localhost:15001/v2/screen-run \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{
    "preset":"us_default","as_of_date":"2024-12-31",
    "risk_sensitivity":"standard","valuation_mode":"strict",
    "enable_ai_risk_layer":true,"ai_provider":"chatgpt"
  }'
```

### 性能与降级

- 每家公司 AI 调用 ~2.5s（实测 apiyi gpt-4.1-mini）
- 548 全启用 AI 估计 ~20-30 分钟
- 主 provider 失败自动切备用；两个都失败降级 RULE_ONLY
- 非 JSON 自动重试 1 次

### MiniMax 待充值

`sk-api-` 国内版 endpoint = `api.minimax.chat/v1/text/chatcompletion_v2`，
auth ok 但需账户余额（status_code 1008 = 余额不足）。
