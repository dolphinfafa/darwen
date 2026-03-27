# Darwen 达尔文股票筛选系统

基于达尔文进化论投资方法论的股票筛选系统，覆盖美股与 A 股。

## 核心理念

用「自然选择」的思维筛选股票——能在市场环境中**生存、复制、适应、积累优势**，且**估值合理**的公司，才是值得投资的标的。

## 五大评分维度

| 维度 | 说明 | 因子数 |
|------|------|--------|
| 生存力 Survival | 杠杆、流动性、现金流、盈利质量 | 6 |
| 复制力 Replication | ROIC、增长可持续性、资本配置 | 6 |
| 适应力 Adaptation | 利润弹性、毛利稳定、治理质量 | 6 |
| 优势积累 Moat | 定价权、复利引擎、规模效应 | 6 |
| 估值纪律 Valuation | 估值倍数、安全边际、流动性 | 6 |

30 个因子 → 五维得分 → 加权总分 → 动态分层（Top / Watch / Reject）

## 技术栈

- **后端**: Python 3.10 · FastAPI · SQLAlchemy · MySQL 8.0
- **前端**: Vue 3 · Vite · ECharts
- **数据源**: SEC EDGAR (美股) · akshare (A 股) · yfinance (行情)

## 快速启动

```bash
# 激活环境
conda activate darwen

# 启动后端 API (端口 15001)
uvicorn backend.main:app --host 0.0.0.0 --port 15001 --reload

# 启动前端 (端口 15002)
cd frontend && npx vite --host 0.0.0.0 --port 15002
```

## 项目结构

```
darwen/
├── backend/
│   ├── main.py            # FastAPI 入口
│   ├── api/               # 路由 (screener / company / report / backtest)
│   ├── factors/           # 30 因子计算引擎
│   ├── scoring/           # 评分 + 红线 gating + 分层
│   ├── pipeline/          # 数据管道 (SEC / A股 / 行情)
│   ├── backtest/          # 回测模块
│   └── models/            # ORM 模型
├── frontend/              # Vue 3 SPA
│   └── src/views/         # Screener / CompanyDetail / BatchReport
├── migrations/            # Alembic 数据库迁移
└── milestones/            # 工作进度文档
```

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端 | https://dev-cn-01.yios.cn/darwen/ |
| API 文档 | http://127.0.0.1:15001/docs |
