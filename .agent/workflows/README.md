# Darwen Agent Workflows

本目录定义 Agent 在 Darwen 项目中执行不同任务时的标准操作流程（SOP）。

## 文件清单

| 工作流 | 用途 |
|---|---|
| `v2-implementation-roadmap.md` | V2 三层漏斗系统的剩余实施路线图（M2-M7） |
| `data-ingestion.md` | 数据接入工作流（SEC / Polygon / Tushare） |
| `metric-computation.md` | 指标预计算工作流（ROCE 等） |
| `ai-risk-layer.md` | AI 风险层调用、prompt 版本管理、失败回退 |
| `screening-funnel.md` | 三层漏斗筛选执行流程 |
| `backtest-pit.md` | 点时回测工作流 |

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

### 端口

- 后端 API：15001（zheyang 用户范围 15000-19999）
- 前端 dev：15002
- 占用查询：`curl -s http://localhost:555/api/summary`
- 严禁占用其他用户范围端口
