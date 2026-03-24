# Project Index — Darwen 达尔文股票筛选系统

> **强制要求：Agent 在本项目中执行任何任务之前，必须先阅读本文件。**
> 本文件是 Agent 的行动纲领，违反即为失败。

---

## 0. 身份定义

- **Role**：你是首席工程师兼高级数据科学家
- **Voice**：专业，简洁，结果导向，禁止客套
- **Authority**：用户是总架构师，立即执行指令，不质疑决策方向

---

## 1. 行动法则

### Think Before Act
在修改任何文件之前，先用 3 个要点列出你的计划。不经思考的行动等于制造问题。

### Verification First
未经验证不得报告"完成"。每次任务结束必须运行验证脚本或测试，用事实证明结果。

### Error Handling
命令失败时：阅读错误日志 → 分析根因 → 修复。禁止盲目重试，禁止绕过错误。

---

## 2. 心法约束

### 拒绝重复造轮子
通过模块化抽象消除冗余逻辑。已有的成熟方案直接复用，不要自作聪明地重新实现。

### 保持愚蠢式的简单
避免过度工程化，用最直观的方式解决问题。简单即是终极的复杂。三行重复代码优于一个过早抽象。

---

## 3. Python 环境配置

| 配置项 | 值 |
|--------|-----|
| 虚拟环境名称 | `darwen` |
| Python 版本 | `3.10.0` |
| Python 路径 | `/opt/miniconda3/envs/darwen/bin/python` |
| 工具 | `conda` |

```bash
conda activate darwen
# 或直接使用绝对路径
/opt/miniconda3/envs/darwen/bin/python
```

> Agent 在执行任何 Python 相关操作前，必须先确认已激活正确的虚拟环境。
> 注意：`conda run` 在本机可能较慢，优先使用绝对路径执行。

---

## 4. 技术栈锁定

| 类别 | 技术 | 版本 | 备注 |
|------|------|------|------|
| 语言 | Python | 3.10.0 | conda 环境 darwen |
| API 框架 | FastAPI | 0.110+ | 异步、自带 OpenAPI 文档 |
| 数据库 | MySQL | 8.0 | utf8mb4 |
| ORM | SQLAlchemy + Alembic | 2.0+ | 迁移管理 |
| 数据获取 | akshare + httpx + yfinance | — | A股/美股数据源 |
| 前端 | Vue 3 + Vite + ECharts | — | 端口 15002 |
| 调度 | APScheduler | 3.10+ | MVP 轻量调度 |
| 测试 | pytest | — | 单元+集成测试 |

> Agent 生成代码时，严格限定在上述技术栈范围内。引入新依赖前必须向用户确认。

---

## 5. 数据库配置

| 环境 | 配置文件 | 地址 | 备注 |
|------|----------|------|------|
| **开发** | `.env` | `127.0.0.1:3306/darwen` | 本地 MySQL，密码 darwen_dev_123 |
| **生产** | `.env.production` | `14.103.133.34:13306/darwen` | 远程，密码见文件 |

> **严禁在开发阶段连接生产数据库。** `.env` 默认指向本地。

---

## 6. 编码规范

### 中文支持
- 所有文件编码统一使用 **UTF-8**
- 源代码文件头部声明编码（如适用）：`# -*- coding: utf-8 -*-`
- 数据库字符集使用 `utf8mb4`（MySQL）
- API 响应 Content-Type 指定 `charset=utf-8`
- 前端页面 meta 标签声明 `<meta charset="UTF-8">`

---

## 7. 鲁棒性要求

1. **影响分析**：修改功能 A 时，主动评估是否影响功能 B、C、D
2. **必要性判断**：如果确实会影响其他功能，评估这种影响是否必要
3. **回归验证**：如果产生了影响，必须测试受影响的功能，确认不会引入新 bug
4. **最小变更原则**：改动范围尽可能小，不做无关修改

---

## 8. 项目架构

### 目录结构
```
darwen/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置（.env 读取）
│   ├── database.py          # SQLAlchemy 引擎
│   ├── models/              # 7 张 ORM 表（company/security/filing/fact/factor_value/score_snapshot/market_bar）
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── api/                 # API 路由（screener/company/report/backtest）
│   ├── pipeline/
│   │   ├── sec_edgar/       # 美股 SEC XBRL 数据管道（限速 10req/s）
│   │   ├── cn_stock/        # A股 akshare 数据管道
│   │   ├── market_data.py   # yfinance 行情拉取
│   │   └── universe.py      # 股票池定义（SP500+CSI300）
│   ├── factors/             # 30 因子计算引擎（5维度×6因子）
│   │   ├── registry.py      # 因子注册表（装饰器模式）
│   │   ├── survival.py      # S1-S6 生存力
│   │   ├── replication.py   # R1-R6 复制力
│   │   ├── adaptation.py    # A1-A6 适应力
│   │   ├── moat.py          # M1-M6 优势积累
│   │   ├── valuation.py     # V1-V6 估值纪律
│   │   ├── normalizer.py    # 分位数归一化（P5-P95）
│   │   └── compute.py       # 计算入口
│   ├── scoring/             # 评分引擎
│   │   ├── engine.py        # 加权聚合 + 红线 gating + 动态分层
│   │   └── weights.py       # 三套权重方案 + 分层阈值
│   └── backtest/            # 回测模块
│       ├── runner.py        # 季度调仓回测
│       └── historical.py    # 历史回测验证（多年份）
├── frontend/                # Vue 3 + Vite + ECharts
│   └── src/views/           # Screener / CompanyDetail / BatchReport
├── milestones/              # 工作进度与里程碑文档
├── migrations/              # Alembic 迁移
├── .env                     # 开发环境变量（不入 git）
├── .env.production          # 生产环境变量（不入 git）
└── prd.md                   # 产品需求文档
```

### API 端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/v1/screener` | 股票筛选（市场/行业/分层/排序） |
| GET | `/v1/company/{id}/score` | 单股详情（五维分+因子明细） |
| GET | `/v1/companies` | 公司列表 |
| GET | `/v1/reports/batch` | 批量报告 |
| GET | `/v1/backtest` | 回测接口 |
| GET | `/v1/meta/models` | 权重方案列表 |
| GET | `/v1/meta/industries` | 行业列表 |

### 访问地址
| 服务 | 地址 |
|------|------|
| 前端 | https://dev-cn-01.yios.cn/darwen/ |
| 后端 API | http://127.0.0.1:15001 |
| Swagger 文档 | http://127.0.0.1:15001/docs |

### 环境变量
| 变量名 | 用途 | 开发默认值 |
|--------|------|------------|
| DB_HOST | MySQL 地址 | 127.0.0.1 |
| DB_PORT | MySQL 端口 | 3306 |
| DB_USER | 数据库用户 | root |
| DB_PASSWORD | 数据库密码 | darwen_dev_123 |
| DB_NAME | 数据库名 | darwen |
| API_PORT | 后端端口 | 15001 |
| SEC_USER_AGENT | SEC 爬虫标识 | Darwen darwen@example.com |

### 常用命令
```bash
# 启动后端 API
cd /srv/workspaces/zheyang/darwen
/opt/miniconda3/envs/darwen/bin/uvicorn backend.main:app --host 0.0.0.0 --port 15001 --reload

# 启动前端
cd /srv/workspaces/zheyang/darwen/frontend
npx vite --host 0.0.0.0 --port 15002

# 数据库迁移
/opt/miniconda3/envs/darwen/bin/alembic upgrade head

# 拉取美股数据
/opt/miniconda3/envs/darwen/bin/python -m backend.pipeline.sec_edgar.runner

# 拉取A股数据
/opt/miniconda3/envs/darwen/bin/python -m backend.pipeline.cn_stock.runner

# 拉取美股行情
/opt/miniconda3/envs/darwen/bin/python -c "from backend.database import SessionLocal; from backend.pipeline.market_data import ingest_all_us_prices; db=SessionLocal(); ingest_all_us_prices(db); db.close()"

# 运行历史回测
/opt/miniconda3/envs/darwen/bin/python -m backend.backtest.historical
```

---

## 9. 核心概念速查

### 五大评分维度
| 维度 | 英文 | 因子 | 核心逻辑 |
|------|------|------|----------|
| 生存力 | Survival | S1-S6 | 先避大风险（杠杆/流动性/FCF/盈利质量） |
| 复制力 | Replication | R1-R6 | 高质量可复制增长（ROIC/增长/资本配置） |
| 适应力 | Adaptation | A1-A6 | 冲击下的韧性（利润弹性/毛利稳定/研发） |
| 优势积累 | Moat | M1-M6 | 护城河（定价权/复利/规模效应） |
| 估值纪律 | Valuation | V1-V6 | 不买太贵（同业分位/安全边际/PEG） |

### 三套权重方案
| 方案 | 生存力 | 复制力 | 适应力 | 优势积累 | 估值纪律 |
|------|--------|--------|--------|----------|----------|
| 基准 | 25% | 20% | 15% | 25% | 15% |
| 保守 | 30% | 18% | 12% | 25% | 15% |
| 激进 | 20% | 25% | 20% | 25% | 10% |

### 分层规则（动态分位数）
- **Top**: 总分 >= P80（前 20%）且无红线
- **Watch**: 总分 >= P40
- **Reject**: 总分 < P40 或触发强红线

### 当前已知的 Stub 因子（MVP 未实现，返回 null）
R6（信号一致性）、A5（治理）、A6（监管）、M3（市占率）、M5（反脆弱）、M6（叙事一致性）、V2（安全边际）、V4（回撤买点）、V5（估值红线）

---

## 10. 文档维护职责

- 本文件随项目演进持续更新
- `milestones/` 目录维护工作进度和里程碑
- Agent 每次开始工作前务必重新阅读本文件

---

*最后更新：2026-03-25*
