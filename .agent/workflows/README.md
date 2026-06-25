# Darwen Agent Workflows

本目录定义 Agent 在 Darwen 项目中执行不同任务时的标准操作流程（SOP）。

## 文件清单

| 工作流 | 用途 |
|---|---|
| `v2-implementation-roadmap.md` | 路线图 + **现行架构（三层全自动漏斗；2026-06-24~25 风险指标融入漏斗 = 原著四类风险全量化/硬事实落点）**；历史 M2-M7 供追溯 |
| `data-ingestion.md` | 数据接入工作流（SEC / Polygon / Tushare） |
| `metric-computation.md` | 指标预计算工作流（ROCE 等） |
| `ai-risk-layer.md` | AI 风险层调用、prompt 版本管理、失败回退 |
| `screening-funnel.md` | 三层漏斗筛选执行流程 |
| `backtest-pit.md` | 点时回测工作流 |

> **现行筛选引擎**：`backend/screening/funnel_v2.py`（ROCE→稳健性→风险性 三层全自动连跑；
> 2026-06-20 起 `auto_advance` 默认开，人工 gate 的 HTTP 层 `/advance`、`/manual` 已移除）。
> AI 双层：`ai/orchestrator.analyze_layer(layer=sturdiness|risk)`。
> **我的股票池（前端首页）**：`api/watchlist.py` + `MyWatchlist.vue`，平铺无分组、展示最新收盘价 +
> 真 TTM 市盈率；按需拉取行情 `services/quote.py`（进详情页/股票池时拉，当天去重+容错）。
> 漏斗结果页 `FunnelResults.vue`：三层手风琴折叠 + 多维搜索过滤。
> **MCP server**（`backend/mcp_server.py`，挂 `/v2/mcp` → `https://<域名>/darwen/v2/mcp/`）：外部 agent 凭
> per-user 令牌（`MCP.vue` 页面 `/mcp` 生成，`user.mcp_token_hash`）读股票池最新价/PE，工具 `list_watchlist_quotes`。
> **财报出处**：美股 `/v2/company/{id}/filing-url`（公开，302→SEC 10-K）；A股靠 Tushare `anns_d` 公告逐年年报
> 直链巨潮（`text_document` doc_type=annual → detail 的 `cn_filings`）。
> **资讯**：anns_d 个股公告入 `text_document` 喂 A股 AI 风险层；`major_news` 全市场入 `market_news`（市场资讯页 `/market-news`）。
> 旧 Q/R/V（`funnel.py`/`v_layer.py`、`ScreenConfig.vue`/`ScreenResults.vue`）保留 deprecated。
> **风险指标融入漏斗（2026-06-24~25）**：原著四类风险全部有量化/硬事实落点，**硬事实优先于 AI**——
> 财务→稳健层 8 指标（`risk_v1`/`solvency_v1`）；治理→风险层硬事实（`governance_signal`：美股 8-K + A股 Tushare 质押/管理层）；
> 行业→稳健层 peer 自建（`industry_v1`）；商业→稳健层客户/供应商集中度 + segment HHI（`commercial_v1`，
> `backend/pipeline/commercial/` 从 10-K iXBRL / Tushare `fina_mainbz` 零采购抽取）。
> 阈值 `config.py`、消费 `funnel_v2._eval_sturdiness`/`_eval_governance_facts`、回填 `scripts/backfill_commercial_signals.py`。
> 详见 `milestones/2026-06-24-phase2.md`、`2026-06-25-phase3.md`、`prd/Darwen_筛选逻辑与数据来源.md`。
> 详见 `milestones/2026-06-21.md`（前端 UX + 估值口径）、`2026-06-20.md`（全自动架构）、`2026-06-18.md`（层定义）。

## 通用规则

### 启动前必读

1. `.claude/claude.md` — 项目级 Agent 指南
2. `prd/v2.0/Darwen_V2_PRD_Master.md` — 当前 V2 PRD
3. `milestones/<latest>.md` — 最近一次工作记录（了解阻塞与进度）

### 修改前必备

1. 用 3 个要点列出计划
2. 跑相关单测/验证脚本
3. 改完后立即写 milestone 记录变更

### 数据库操作

- 所有 schema 变更必须经 Alembic 迁移
- 严禁直接 `ALTER TABLE`、`DROP TABLE`
- 迁移前先打 git tag 备份

### Python 环境

- 虚拟环境：`/opt/miniconda3/envs/darwen/bin/python`
- 依赖：`requirements.txt`
- 新增依赖前必须征得用户同意

### 端口（2026-05-15 修正）

- **后端 API：15003**（V2 实际端口；15001 已被 punkrecord 长期占用）
- 前端 dev：15002（root dev_web vite 反代 base=/darwen/）
- 占用查询：`curl -s http://localhost:555/api/summary`
- 严禁占用其他用户范围端口
- nginx `/darwen/v1/` 和 `/darwen/v2/` 反代到 `127.0.0.1:15003`
