# Project Index — Darwen 达尔文股票筛选系统

> **强制要求：Agent 在本项目中执行任何任务之前，必须先阅读本文件。**
> 本文件是 Agent 的行动纲领，违反即为失败。

---

## 最高编码原则（优先级高于本文件其余所有条款）

每次变更都必须保持正确性、安全、隐私、数据完整性、兼容性、外部硬性要求，以及明确的性能/SLA 约束。

在不突破这些底线的前提下，致力于将未来维护者理解、验证、审查、修改、诊断、操作、删除和接手代码时的总认知成本和风险降至最低。

每次变更都不能让相关影响面（包含所有可能被影响假设的产物或契约，不仅是编辑过的文件）更难验证、理解、修改、评审、删除、诊断、恢复、追溯或运维。并要在可行时进行改善。
只要触碰热点代码，除非会违背底线，否则必须降低任务暴露出的特定维护成本。
优先选择小步、局部、显式、行为经验证且可逆的变更。
除非确有理由证明长期成本更低，否则不要引入不必要的抽象、依赖、大重写、兼容性破坏或新项目模式。

消除偶然复杂度。让本质复杂度显式、有界、可验证且可追溯。

### 质量视角

#### 1. 易验证

变更后的行为应有清晰边界，且验证成本低。

修复缺陷时，尽量先保留或补齐能复现问题的证据，再增加或更新能证明修复有效的测试/检查。
使用最轻量但足够充分的组合：测试、类型检查、断言、契约、可复现步骤或验收标准。

验证力度要与风险、影响范围、模糊程度、不可逆性、外部暴露程度相匹配。
优先使用具有足够独立性的验证方式，以便能发现自身误解，而非只证明代码能跑通。

#### 2. 易理解

代码应通过命名、结构、控制流、类型和领域语言直接表达意图。

避免隐式约定、魔数、炫技、不必要的间接层、深层嵌套、隐藏状态，以及需要跨很多文件才能理解的逻辑。

输入、输出、所有权、状态转移、不变量和副作用都应尽量显式。
遵循项目已有惯例，除非有充分理由。

#### 3. 易局部修改、审查和删除

设计变更时，要让未来修改或删除能集中发生在少数明确的位置。

保持清晰接口、单一职责、低耦合、可控副作用和小而完整的改动。
只有当抽象能简化当前已验证行为，或消除真实重复/耦合时，才新增抽象；不要为了假想需求提前设计。

重构时不要改变对外表现行为，除非行为变更是有意为之、有文档记录并经过验证。

避免大范围重写、顺手清理、格式变动、无关重命名或架构调整，除非当前任务确实需要。

#### 4. 易诊断和恢复

失败路径应保留足够上下文，方便定位和恢复，同时不暴露敏感数据。

错误信息、日志、指标、追踪信息、校验消息和降级逻辑应使边界失败、无效状态及外部依赖故障易于识别。

对于持久化数据、迁移、外部系统、后台任务、重试与不可逆操作，要考虑幂等、部分失败、回滚、恢复和安全降级。

#### 5. 易追溯和接管

对于并非显而易见的约束、权衡、兼容性考量、迁移步骤、操作风险、历史背景、被否决方案和已知限制，应记录在最持久且最合适的地方：测试、注释、提交信息、设计提案、架构概览、运维手册或 ADR。

不要重复解释代码已清楚表达的事实。
记录为何做出出人意料的选择、哪些必须保持兼容、哪些不能随意改动、代码有意不做什么、以及未来维护者应先看哪里。

如果工作未完成、风险较高或仍有不确定性，必须留下交接说明：当前状态、已做的尝试、假设、走过哪些死路、已执行的验证、剩余风险以及下一步最安全的操作。

### 变更纪律

编辑前，先检查相关的现有模式、契约、测试、调用方和兼容性边界。
优先选择能满足需求的最小完整改动。

不要凭空发明 API、数据契约、配置项、环境假设、产品需求、迁移语义或依赖行为。

能用小巧清晰的本地实现解决就不要引入新依赖。
必须加依赖时，需说明其如何降低总认知和运维成本，并相应更新锁文件和相关配置。

需求或行为模糊不清时，尽量维持原有行为，写明假设，避免不可逆改动。

认为工作完成前，报告：
- 更改了什么以及原因；
- 哪些行为发生了变化；
- 哪些行为被刻意保留；
- 添加或运行了哪些验证；
- 还剩哪些风险、假设或限制；
- 是否涉及安全、隐私、数据完整性、兼容性、迁移、依赖、回滚或运维相关问题。

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

### Stub 因子状态
Phase 2 P0 已补齐全部 9 个 stub 因子（使用财务数据代理实现，未来 LLM 升级时可替换）：
R6（信号一致性→收入/利润/OCF方向一致性）、A5（治理→稀释+OCF/NI+分红）、A6（监管→8-K占比）、
M3（市占率→log(Rev)×CAGR）、M5（反脆弱→逆周期capex）、M6（叙事一致性→收入利润同向变化率）、
V2（安全边际→FCF Yield×(1+ROA)）、V4（回撤买点→6月最大回撤）、V5（估值红线→Earnings Yield+连续亏损检测）

### 红线一票否决机制
即使总分很高，触发以下任一强红线即归入 Reject：
- `interest_coverage_below_1.5`：利息保障倍数 < 1.5x（偿债风险）
- `high_dilution_above_30pct`：3年股权稀释 > 30%（融资激进）
- `net_debt_ebitda_above_4`：净负债/EBITDA > 4x（高杠杆）
- `consecutive_loss_with_negative_roe`：连续亏损（盈利风险）

### 因子辅助函数
- `get_revenue(db, company_id, asof)` — 统一取收入值，兼容 Revenues / RevenueFromContractWithCustomerExcludingAssessedTax / revenue
- `get_revenue_series(db, company_id, years, asof)` — 统一取年度收入序列
- `get_close_prices(db, company_id, asof, days)` — 取行情收盘价序列
- `get_volume_series(db, company_id, asof, days)` — 取成交量序列
- `get_filing_count(db, company_id, asof, form_types, years)` — 统计 filing 数量

### 前端交互功能
- CompanyDetail 页面：每个维度旁有 ⓘ 图标，点击弹窗显示维度说明 + 因子列表 + 权重分配
- 每个维度分数可点击展开，查看 6 个子因子的原始值和归一化分
- 红线触发时总分旁显示红色警告标签（如 "⚠ 股权稀释 > 30%"）
- 因子明细表的数据溯源列解析 Python dict 为中文可读标签

---

## 10. 文档维护职责

- 本文件随项目演进持续更新
- `milestones/` 目录维护工作进度和里程碑
- Agent 每次开始工作前务必重新阅读本文件

---

*最后更新：2026-03-25*
