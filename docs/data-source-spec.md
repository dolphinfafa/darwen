# Darwen 数据源规范（Data Source Specification）

> 最后更新：2026-03-29

## 数据源分级

| 级别 | 定位 | 特点 |
|------|------|------|
| **L1 官方真值源** | 法定披露、时间戳权威 | 可追溯、修订可追踪 |
| **L2 商业结构化源** | 标准化字段、稳定API | 口径统一、覆盖完整 |
| **L3 开发备份源** | 原型验证、低成本实验 | 免费但不保证稳定 |

---

## 美股数据源栈

| 用途 | L1 | L2 | L3 |
|------|----|----|-----|
| **财报** | SEC EDGAR XBRL | — | — |
| **Filing/事件** | SEC 8-K/10-K/10-Q | — | — |
| **行情** | — | Polygon | yfinance |
| **估值/股本** | SEC companyfacts | Polygon Fundamentals | — |
| **行业分类** | SEC SIC | — | — |

### 当前状态
- SEC EDGAR：**已接入**，50个XBRL科目，201家公司
- yfinance：**已接入**，134万条日线（L3，生产需升级到Polygon）
- Polygon：**待接入**

---

## A股数据源栈

| 用途 | L1 | L2 | L3 |
|------|----|----|-----|
| **财报** | 巨潮资讯网 / 交易所公告 | Wind / iFinD / CSMAR | akshare |
| **公告/监管事件** | 巨潮 / 上交所 / 深交所 | Wind | — |
| **行情** | — | Wind / iFinD | akshare |
| **估值/股本** | 交易所公告 | Wind / iFinD | akshare |
| **行业分类** | — | Wind(申万) / iFinD | akshare |

### 当前状态
- akshare：**已接入**（L3，原型层），三大报表 + 后复权日线，50家公司
- 巨潮：**待接入**
- Wind / iFinD：**待接入**（需付费）

---

## 字段级主源映射

### 核心财务字段

| 字段 | 美股主源 | 美股备选 | A股主源（目标） | A股当前 |
|------|---------|---------|----------------|---------|
| Revenue | SEC XBRL | — | Wind/iFinD | akshare |
| EBIT / Operating Income | SEC XBRL | — | Wind/iFinD | akshare |
| Net Income | SEC XBRL | — | Wind/iFinD | akshare |
| Total Assets | SEC XBRL | — | Wind/iFinD | akshare |
| Current Liabilities | SEC XBRL | — | Wind/iFinD | akshare |
| Current Assets | SEC XBRL | — | Wind/iFinD | akshare |
| Cash | SEC XBRL | — | Wind/iFinD | akshare |
| OCF | SEC XBRL | — | Wind/iFinD | akshare |
| Capex | SEC XBRL | — | Wind/iFinD | akshare |
| Interest Expense | SEC XBRL | — | Wind/iFinD | akshare(不稳定) |
| Shares Outstanding | SEC XBRL | — | Wind/iFinD | akshare |
| Gross Profit | SEC XBRL(51%) | — | Wind/iFinD | akshare(78%) |
| R&D Expense | SEC XBRL(58%) | — | Wind/iFinD | akshare(78%) |
| Goodwill | SEC XBRL | — | Wind/iFinD | akshare |
| Debt (LT+ST) | SEC XBRL | — | Wind/iFinD | akshare |

### 行情/估值字段

| 字段 | 美股主源 | 美股当前 | A股主源（目标） | A股当前 |
|------|---------|---------|----------------|---------|
| 收盘价（复权） | Polygon | yfinance | Wind/iFinD | akshare(后复权) |
| 收盘价（不复权） | Polygon | yfinance | Wind/iFinD | akshare实时取 |
| 成交量 | Polygon | yfinance | Wind/iFinD | akshare |
| 总股本时间序列 | SEC | yfinance | Wind/iFinD | akshare |
| 点时市值 | Polygon | 手动算 | Wind/iFinD | 手动算 |
| TTM PE | Polygon Fundamentals | 手动算 | Wind/iFinD | 手动算 |

### 监管/事件字段

| 字段 | 美股主源 | A股主源（目标） | A股当前 |
|------|---------|----------------|---------|
| 定期报告(10-K/年报) | SEC EDGAR | 巨潮 | 无 |
| 重大事件(8-K) | SEC EDGAR | 巨潮 | 无 |
| 审计意见 | SEC 10-K | 巨潮/年报 | 无 |
| CEO/CFO变更 | SEC 8-K | 巨潮/公告 | 无 |
| 立案调查/处罚 | SEC enforcement | 交易所/证监会 | 无 |
| 控股股东质押 | — | 巨潮/交易所 | 无 |
| 业绩预告/快报 | — | 巨潮/交易所 | 无 |

---

## 升级优先级

### P0（立即可做）
1. 接入 Polygon 免费层替代 yfinance（美股行情）
2. A股行情加入不复权价格存储（估值计算用）

### P1（需付费）
1. 接入 Wind 或 iFinD（A股结构化财务+行情+行业）
2. 升级 Polygon 到付费层（历史完整数据）

### P2（增强）
1. 接入巨潮公告 API（A股法定披露）
2. 接入 SEC EDGAR full-text（审计意见、内控）
3. Nasdaq Data Link 作为机构级补充

---

## 已知数据质量问题

| 问题 | 影响 | 状态 |
|------|------|------|
| akshare 前复权负价格 | A股历史图表 | **已修复**（改后复权） |
| A股后复权价格非真实价格 | PE计算虚高 | **已修复**（详情页用不复权实时价） |
| 美股 GrossProfit 覆盖率 51% | M1/A2/R4 因子NULL率高 | 待升级 |
| A股 interest_expense 不稳定 | 利息保障计算受影响 | 待升级 |
| 无审计意见/管理层变更数据 | V1.0治理模块缺失 | 待 P2 接入 |

---

*本文件由项目维护，每次数据源变更后更新。*
