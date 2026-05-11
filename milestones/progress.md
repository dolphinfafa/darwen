# Darwen 项目进度总览

> 最后更新：2026-05-11
> 项目方向：V2 三层漏斗股票筛选系统（基于 Pulak Prasad《What I Learned About Investing from Darwin》）

---

## 项目状态：V2 M2 ROCE 落地完成，待续 M2.3+

---

## V2 里程碑进度

| # | 里程碑 | 状态 | 关键交付 |
|---|---|---|---|
| M1   | 数据基础（schema 重构、Tushare Pro 接入、10 家 A 股蓝筹回填） | ✅ | 6 张 V2 表 + Tushare 字段 canonical 化 |
| M1.x | SEC 字段修补（CORE_CONCEPTS 扩 7 tag、546 美股重拉） | ✅ | STI / LongTermDebtCurrent / OperatingLease 等入库 |
| M2.1 | 字段映射 & helpers | ✅ | field_map（24 canonical 三向映射）+ helpers（4 API） |
| M2.2 | ROCE 严格口径 + 5Y/10Y 门槛 | ✅ | roce.py + QualityGate（含 Q5_RECENT_NEG_CAP 修正） |
| M2.5 | ROCE 落库调度 + 全量回填 | ✅ (ROCE 部分) | 598 家 OK / 31,423 年度行 / 32,161 血缘 / 25.6% 通过 |
| M2.3 | 杠杆 / 现金质量 | ⏳ | leverage.py + cash_quality.py |
| M2.4 | 稀释 / 估值 | ⏳ | dilution.py + valuation.py |
| M3   | 三层漏斗（Q / R / V Layer） | ⏳ | screening 模块 + reason_codes + 5 状态 |
| M4   | AI 风险层（ChatGPT + MiniMax + Fernet） | ⏳ | ai 模块 |
| M5   | API 层重写（V2 endpoints + Key 绑定） | ⏳ | screening/backtest/user_settings router |
| M6   | 前端 6 页面重构 | ⏳ | UniverseConfig / ScreenConfig / Results / AccountSettings 等 |
| M7   | 月度再平衡回测 + 端到端 smoke | ⏳ | backtest/v2_engine.py + E1/E2/E6 实验 |
| M1.9 | SEC filing 文本与元数据 | ⏳ (可与 M2.x 并行) | filings_text.py |
| M1.10| Polygon News 接入 | ⏳ (可与 M2.x 并行) | news/polygon_news.py |

---

## 数据资产（截至 2026-05-11）

| 表 | 行数 | 说明 |
|----|---:|------|
| fact (SEC) | 1,074,000+ | 含新增 7 个 tag 重拉数据 |
| fact (TS-FS) | 13,874 | A 股新数据 10 家蓝筹 |
| fact (AKSHARE) | 26,629 | A 股旧数据 50 家（M2 fallback） |
| company | 598 | 548 美股 + 50 A 股 |
| metric_periodic | 33,411 | ROCE 相关年度 + 截面指标 |
| metric_lineage_log | 32,161 | 每输入字段一行血缘记录 |
| market_bar | 474,808 | 2008-2026 美股日线（V1 遗留，V2 待延伸） |

---

## ROCE 全量回填验收结果（M2.5 ROCE 部分）

### 通过率

- 通过 5Y 门槛 (Q3 PASS)：153 / 598 = **25.6%**
- 强通过 (10Y 强 track record)：129 / 598 = **21.6%**
- 与 Pulak 书"严苛筛选"预期吻合

### fail_reason 分布

| reason | count | 含义 |
|---|---:|---|
| 通过 (NULL) | 153 | Q3 通过 |
| Q5_RECENT_NEG_CAP_OR_MISSING | 177 | 近 5 年 ≥ 2 年负营运资本 / 字段缺，走 P1 人工覆核（Apple/Visa 等大现金公司） |
| Q3_FAIL_MEDIAN | 107 | 5Y ROCE 中位数 < 20% |
| Q1_INSUFFICIENT_HISTORY | 43 | 财年不足 5 年 |
| Q3_FAIL_COUNT | 17 | 中位数过线但 ≥ 20% 年数 < 4 |

### 算法抽样验证

| 公司 | 5Y 中位数 | 状态 | 备注 |
|---|---:|---|---|
| Microsoft | 29.7% | ✓ pass + strong | |
| Nvidia | 39.7% | ✓ pass + strong | |
| Medtronic | 52% | ✓ pass | |
| 茅台 | 66.9% | ✓ pass | |
| 美的集团 | 91.8% | ✓ pass + strong | |
| 泸州老窖 | 105.7% | ✓ pass + strong | |
| Cisco | 22% | ✓ pass (修补前 213% 失真) | |
| Apple | Q5_RECENT_NEG_CAP | 覆核 (修补前 230% 假阳) | |
| Visa | Q5_RECENT_NEG_CAP | 覆核 (修补前 622% 假阳) | |
| 京东方 | 5.2% | Q3_FAIL_MEDIAN | 重资本面板厂 |
| 格力 | NEGATIVE_CAP_EMP | Q5 覆核 | 结构性负 NWC |
| 广发证券 | n/a | Q0 排除 | 券商资产结构 |

---

## 关键技术决策（V2 时期）

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-05-09 | V0/V1 评分体系完全替换 | drop score_snapshot/factor_value 表 + 删 scoring/factors/backtest 目录 |
| 2026-05-09 | A 股数据源切换 Tushare Pro | 用户已升级付费套餐，财报 + 披露日期 + daily_basic 全有 |
| 2026-05-09 | 旧 30 因子加权评分弃用 | PRD V2 改为五状态 + reason_codes，不输出综合总分 |
| 2026-05-09 | AI Key 用户表加密存储 | Fernet + DARWEN_FERNET_KEY，每用户独立计费 |
| 2026-05-09 | ChatGPT 5 + MiniMax 2.7 双 provider | M4 实现 |
| 2026-05-11 | fact.account_code 退化兼容 | M1 重构时退化为字面 taxonomy 名，helpers 改用 concept 查实际 tag |
| 2026-05-11 | helpers 跨 source 自动回退 | A 股 TS-FS → AKSHARE，US 仅 SEC |
| 2026-05-11 | 严格年报模式 | annual_only=True + fiscal_year_end_month 精确匹配，避免季报混入 |
| 2026-05-11 | ROCE 缺失字段降级标签 | EXCESS_CASH_PROXY_LOW_CONFIDENCE / NEGATIVE_OR_ZERO_CAPITAL_EMPLOYED / EBIT_FROM_OP_INC_PLUS_INTEREST 等 |
| 2026-05-11 | Quality Gate 窗口取"最近 5 完整财年"含 invalid | 避免 Apple/Visa 等用早期 valid 年补窗口假阳通过 |
| 2026-05-11 | SEC CORE_CONCEPTS 扩 7 tag | ShortTermInvestments / MarketableSecuritiesCurrent / LongTermDebtCurrent 等是 ROCE 公式必需 |
| 2026-05-11 | formula_version 字段 | metric_periodic 唯一键含 formula_version，便于未来 ROCE 口径升级共存 |

---

## 主要参考文档

- `prd/v2.0/Darwen_V2_PRD_Master.md` — V2 PRD（权威）
- `milestones/v2-plan.md` — M2-M7 完整实施规划
- `.agent/workflows/v2-implementation-roadmap.md` — Agent 执行 SOP
- `milestones/2026-05-09.md` — M1 完成记录
- `milestones/2026-05-11.md` — M2 ROCE 落地记录

---

*本文件由 Agent 维护，反映项目最新状态。*
