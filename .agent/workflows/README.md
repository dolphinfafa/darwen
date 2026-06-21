# Darwen Agent Workflows

本目录定义 Agent 在 Darwen 项目中执行不同任务时的标准操作流程（SOP）。

## 文件清单

| 工作流 | 用途 |
|---|---|
| `v2-implementation-roadmap.md` | 路线图 + **现行架构（三层全自动漏斗；2026-06-21 我的股票池首页 + 最新价/真 TTM PE + 漏斗手风琴）**；历史 M2-M7 供追溯 |
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
> 旧 Q/R/V（`funnel.py`/`v_layer.py`、`ScreenConfig.vue`/`ScreenResults.vue`）保留 deprecated。
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
