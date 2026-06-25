# Darwen 达尔文股票筛选系统

基于 Pulak Prasad《What I Learned About Investing from Darwin》投资方法论的股票筛选系统，覆盖美股与 A 股。

## 核心理念

用「自然选择」的思维筛选股票——**少买、买好、长持**。先用高门槛锁定极少数优质公司，
再层层排除「不稳健」与「有红旗」的标的，宁可错过、不可买错。

## 三层全自动漏斗（V2 现行架构）

筛选引擎 `backend/screening/funnel_v2.py`，ROCE → 稳健性 → 风险性 三层自动连跑，逐层排除：

| 层 | 作用 | 判定方式 |
|----|------|----------|
| **① ROCE 质量层** | 锁定高资本回报的「好生意」 | 规则：ROCE 门槛 + 回溯年数（可配 3/5/7/10）|
| **② 稳健性层** | 排除「不稳健」公司 | 规则（财务/行业/商业量化指标）+ AI 兜底 |
| **③ 风险性层** | 排除「治理/管理红旗」 | 硬事实（法定披露）优先 + AI 佐证 |

> 存活语义：`screen_result.rejected_at_layer IS NULL` 即当前存活/最终入选；每层只处理存活集，计数守恒。

## 风险指标体系（原著四类风险，全量化/硬事实落点）

「硬事实优先于 AI」——有数据按规则判定，无数据才回落 AI：

| 风险类别 | 落点 | 实现 |
|---|---|---|
| **财务风险** | 稳健层 8 指标 | 应计利润率 / FCF 波动（`risk_v1`）、Altman Z'' / 应收存货增速领先 / CCC 恶化（`solvency_v1`）|
| **治理风险** | 风险层硬事实 | 美股 8-K（重述/审计师/高管动荡）+ A股 Tushare（质押/一把手离任）→ `governance_signal` |
| **行业风险** | 稳健层 peer 对标 | 自建同市场同行业营收 CAGR 中位（`industry_v1`），相对落后预警、极端落后剔除 |
| **商业风险** | 稳健层商业深度 | 客户/供应商集中度 + segment 收入 HHI（`commercial_v1`），零采购从 10-K iXBRL / Tushare `fina_mainbz` 抽取 |

> 各量化指标 hard（剔除）/ soft（观察区）/ pass 三档分档，软警告叠加达阈值升级硬剔除；阈值随 `risk_sensitivity`（strict/standard/loose）调整。
> 详见 `prd/Darwen_筛选逻辑与数据来源.md`。

## 技术栈

- **后端**: Python 3.10 · FastAPI · SQLAlchemy · MySQL 8.0 · Alembic
- **前端**: Vue 3 · Vite · ECharts
- **数据源**: SEC EDGAR（美股财报/8-K/10-K 含 iXBRL）· Tushare（A股财报/公告/质押/主营构成）· Polygon（美股新闻）· yfinance（行情）
- **AI 风险层**: 可配置 `ai_mode`（off / 仅风险层 / 稳健+风险层全程），证据来自法定披露 + 新闻
- **MCP server**: 外部 agent 凭 per-user 令牌读「我的股票池」最新价/PE（挂 `/v2/mcp`）

## 快速启动

```bash
# 激活环境
conda activate darwen

# 启动后端 API（端口见 .env API_PORT，开发 15003 / 生产 15001）
uvicorn backend.main:app --host 0.0.0.0 --port 15003 --reload

# 启动前端（端口 15002）
cd frontend && npx vite --host 0.0.0.0 --port 15002
```

## 项目结构

```
darwen/
├── backend/
│   ├── main.py            # FastAPI 入口
│   ├── api/               # 路由 (screening / companies / watchlist / backtest / auth)
│   ├── screening/         # 三层漏斗引擎 funnel_v2 + 阈值 config + 原因标签
│   ├── metrics/           # 点时指标预计算 (ROCE / 偿付 / 现金质量 / 行业 peer)
│   ├── pipeline/          # 数据管道
│   │   ├── sec_edgar/     #   美股 SEC (companyfacts / filings_text)
│   │   ├── cn_stock_v2/   #   A股 Tushare
│   │   ├── governance/    #   治理硬事实 (8-K / Tushare 质押·管理层)
│   │   ├── commercial/    #   商业深度 (10-K 客户/供应商集中度 + segment HHI)
│   │   └── news/          #   Polygon 新闻
│   ├── ai/                # AI 风险层 orchestrator (稳健 + 风险双层)
│   ├── backtest/          # 点时回测模块
│   ├── services/          # 行情按需拉取 / 估值快照
│   ├── mcp_server.py      # MCP server (外部 agent 读股票池)
│   └── models/            # ORM 模型
├── frontend/              # Vue 3 SPA (我的股票池首页 / 漏斗结果 / 公司详情 / 市场资讯)
├── scripts/              # 一次性回填脚本 (商业信号 / 营运资本等)
├── migrations/            # Alembic 数据库迁移
├── prd/                   # 产品需求 + 筛选逻辑与数据来源
└── milestones/            # 工作进度文档
```

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端 | https://dev-cn-01.yios.cn/darwen/ |
| API 文档 | http://127.0.0.1:15003/docs |
