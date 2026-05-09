# Darwen PRD Part 3：字段级算法、会计口径映射与研发实现说明

> 目标：将《What I Learned About Investing from Darwin》的核心方法论继续下沉到“字段—口径—过滤—排序—输出”层级，形成可直接替换现有 30 因子模型的研发说明。
>
> 本文严格区分：
> - **原书明确原则 / 明确数字**：直接来自书中表述或可直接复述的投资规则。
> - **产品化补充规则**：为落地双市场股票筛选系统所增加的工程化设计，不等同于作者原文。

---

## 1. 本阶段目标

本部分回答五个问题：

1. 如何把原书方法论映射成字段级算法？
2. 美股与 A 股分别从哪些报表字段取数？
3. 哪些规则应当做成硬过滤，而不是加权打分？
4. 估值该如何进入系统？
5. 结果应该如何输出给用户？

---

## 2. 产品应采用的新模型结构

替换现有“30 因子加权总分”模型，采用四层结构：

```text
Universe
  ↓
Hard Reject Filters（硬过滤）
  ↓
Quality Engine（质量排序）
  ↓
Fair Price Gate（估值闸门）
  ↓
Hold / Monitor（持有与监控）
```

### 2.1 为什么要替换现有模型

现有模型的主要问题：

1. **把本应一票否决的条件做成了可被别的分数抵消的项目**。
   - 例如：长期资本回报不达标、财务脆弱、治理明显恶化，本应直接排除。
2. **把估值做成普通评分项**。
   - 原书更接近“好公司 + 合理价格”的闸门机制，而非“质量 80 分 + 估值 20 分 = 100 分”。
3. **用过多财务因子模拟“进化”**。
   - 原书的重点不是“更多因子”，而是“极少数关键变量 + 长期历史验证”。

---

## 3. 书中原则对应的系统层设计

| 书中思想 | 系统实现层 | 是否为硬规则 |
|---|---|---|
| 长期高资本回报 | Hard Reject + Quality Core | 是 |
| 低商业/财务风险 | Hard Reject | 是 |
| 护城河宽且可持续 | Quality Engine | 否，但高权重 |
| 不做预测，重历史事实 | 全系统 | 是 |
| 估值重要，但不是精确 DCF | Fair Price Gate | 是 |
| 少做决策、长期持有 | Hold / Monitor | 是 |

---

## 4. Hard Reject Filters（硬过滤层）

> 这部分是系统最关键的变化。原书风格不是“所有东西都打分”，而是先把不符合生物进化/资本复利逻辑的公司排除掉。

### 4.1 Filter F1：长期资本回报过滤

#### 原书依据
- 作者明确表示：**长期历史 ROCE 低于 20% 的公司不投**。
- 观察窗口强调 **5–10 年，通常更长**。

#### 产品规则
- **规则**：`avg_roce_5y < 20%` → 直接排除
- **更严格版本**：`avg_roce_10y < 20%` → 直接排除
- 若上市不足 5 年：暂不进入主股票池，仅进入观察池

#### 数据字段

**美股**
- EBIT / Operating Income
- Total Assets
- Current Liabilities
- Cash and Cash Equivalents
- 可选：Net PPE、Goodwill、Intangibles（做口径校验）

**A股**
- 营业利润 / 息税前利润近似项
- 总资产
- 流动负债
- 货币资金

#### 计算口径（推荐）

```text
Capital Employed = Total Assets - Current Liabilities
ROCE = EBIT / Average Capital Employed
```

#### 注意事项
- 若现金占比极高且与主营无关，可在进阶版使用：

```text
Adjusted Capital Employed = Total Assets - Current Liabilities - Excess Cash
```

但初版不建议过度调整，以免跨市场口径不一致。

---

### 4.2 Filter F2：财务脆弱性过滤

#### 原书精神
原书高度强调低财务风险，不喜欢脆弱资产负债表。

#### 产品规则（补充）
下列条件任一满足则排除：

1. `interest_coverage < 3`（若有利息支出字段）
2. `net_debt / operating_profit > 4`
3. `current_ratio < 1` 且连续两年恶化
4. 连续两年经营现金流为负且无明确改善证据

#### 数据字段

**美股**
- Interest Expense
- Cash And Cash Equivalents
- Short-term Debt
- Long-term Debt
- Current Assets
- Current Liabilities
- Cash from Operations

**A股**
- 利息支出（如可得）
- 货币资金
- 短期借款
- 长期借款 / 应付债券
- 流动资产
- 流动负债
- 经营活动产生的现金流量净额

---

### 4.3 Filter F3：利润质量过滤

#### 书中精神
强调历史事实、质量、低风险。利润不能只停留在会计表面。

#### 产品规则（补充）
1. `ocf / net_income < 0.7` 且连续两年成立 → 排除
2. 最近 5 年中有 3 年以上自由现金流为负 → 排除（金融、强周期行业除外）
3. 应收/存货增速显著高于收入增速并连续两年 → 标红或排除

#### 说明
这一条属于产品化补充，但与作者强调“真实经济表现优先于纸面预测”是一致的。

---

### 4.4 Filter F4：治理与稀释过滤

#### 书中精神
原书对资本配置、治理和长期复利很重视。

#### 产品规则（补充）
1. `share_count_cagr_5y > 3%` 且不存在合理再投资解释 → 排除或大幅降级
2. 连续多年高额股权激励稀释但 ROCE 无改善 → 排除
3. 大额频繁并购导致商誉持续膨胀且回报下滑 → 排除

#### 数据字段
- Diluted Weighted Average Shares
- Common Shares Outstanding
- Goodwill
- Intangible Assets
- Cash paid for acquisitions

A 股可用：
- 期末股本 / 总股本
- 商誉
- 无形资产
- 投资活动现金流中的并购相关项目

---

## 5. Quality Engine（质量排序层）

> 通过硬过滤后，再对剩余公司排序。这里不是“面向全市场所有垃圾股打分”，而是“对已通过生存门槛的物种做优中选优”。

建议采用 100 分制，但只对通过硬过滤的公司赋分。

### 5.1 质量引擎的三大主维度

| 维度 | 权重 | 含义 |
|---|---:|---|
| Q1 资本回报质量 | 40 | 长期高 ROCE / 高现金回报 |
| Q2 护城河与稳定性 | 35 | 毛利、利润、现金流、份额稳定 |
| Q3 资本配置与股东友好 | 25 | 再投资、回购、分红、稀释控制 |

> 注：该权重为产品化补充，不是原书原句数字。

---

### 5.2 Q1：资本回报质量（40 分）

#### Q1.1 平均 ROCE（20 分）

```text
score_roce_level =
  20, if avg_roce_10y >= 35%
  16, if avg_roce_10y >= 30%
  12, if avg_roce_10y >= 25%
   8, if avg_roce_10y >= 20%
   0, otherwise
```

#### Q1.2 ROCE 稳定性（10 分）

```text
score_roce_stability = 10 - penalty
penalty 由 10 年 ROCE 标准差决定
```

建议：
- 标准差 < 5pct → 10 分
- 5–8pct → 7 分
- 8–12pct → 4 分
- >12pct → 0 分

#### Q1.3 现金转化（10 分）

```text
cash_conversion = sum(OCF_5y) / sum(EBIT_5y)
```

评分：
- ≥ 0.9 → 10 分
- 0.75–0.9 → 7 分
- 0.6–0.75 → 4 分
- < 0.6 → 0 分

---

### 5.3 Q2：护城河与稳定性（35 分）

#### Q2.1 毛利率稳定性（10 分）

原书重视护城河与高质量生意。毛利率和营业利润率的长期稳定，是重要近似变量。

```text
gross_margin_std_5y
```

评分建议：
- std < 3pct → 10
- 3–5pct → 7
- 5–8pct → 4
- >8pct → 0

#### Q2.2 收入连续性（10 分）

```text
revenue_positive_years_5y
```

评分建议：
- 5/5 年正增长 → 10
- 4/5 年正增长 → 7
- 3/5 年正增长 → 4
- 其他 → 0

#### Q2.3 经营利润率稳定性（10 分）

```text
operating_margin_std_5y
```

评分建议：同毛利率稳定性。

#### Q2.4 周期脆弱性修正（5 分）

对强周期行业采用“行业相对稳定性”而不是绝对稳定性，以避免对资源股、航运股等产生系统性误伤。

---

### 5.4 Q3：资本配置与股东友好（25 分）

#### Q3.1 再投资效率（10 分）

```text
incremental_roce = ΔEBIT / ΔCapitalEmployed
```

评分：
- ≥ 25% → 10
- 15–25% → 7
- 8–15% → 4
- < 8% → 0

#### Q3.2 稀释控制（5 分）

```text
share_count_cagr_5y
```

评分：
- ≤ 0% → 5
- 0–1% → 4
- 1–3% → 2
- >3% → 0

#### Q3.3 股东回报纪律（5 分）

- 回购是否发生在合理估值区间
- 分红是否来源于真实现金流

初版难以完全自动化，建议先用代理变量：

```text
(total_buybacks + dividends) / FCF_5y
```

但要限制在合理区间内解释，避免把“掏空成长”的高分红企业打高分。

#### Q3.4 并购纪律（5 分）

若出现以下情况则扣分：
- 商誉/净资产占比快速抬升
- 并购后 ROCE 下滑
- 大额并购频率过高

---

## 6. Fair Price Gate（估值闸门层）

> 本层不建议做成大权重评分项，而应做成“好公司是否值得现在买”的买入判断层。

### 6.1 原书中的明确估值锚

书中可直接提炼的关键点：

1. **长期市场 trailing PE 大约 19–20x**
2. **作者组合建仓时的中位 trailing PE 为 14.9x**
3. **极少数真正独特的公司，可以接受高十几倍或低二十几倍 PE**
4. 作者明确反对把 DCF 做成“精确到小数点”的伪精确工具

### 6.2 产品估值设计原则

1. 估值不能脱离质量
2. 估值不能独立成“低 PE 越高分”
3. 估值应当是 **按质量分层后的购买纪律**

---

### 6.3 推荐估值闸门逻辑

先根据质量引擎结果将公司分层：

| 质量层级 | 条件 | 允许 PE 区间 |
|---|---|---|
| Tier A | Q >= 85 且 avg_roce_10y >= 30% | 可接受 PE ≤ 22 |
| Tier B | Q 70–84 且 avg_roce_10y >= 25% | 可接受 PE ≤ 18 |
| Tier C | Q 55–69 且 avg_roce_10y >= 20% | 可接受 PE ≤ 15 |
| Tier D | 其他 | 不买 |

> 说明：
> - `22x / 18x / 15x` 为产品化补充，用于将原书“市场 19–20x；大多数买在 14.9x；少数独特公司高十几到低二十几倍也可接受”的思想工程化。
> - 不能声称这是作者明文给出的统一 PE 上限。

---

### 6.4 估值字段

#### 美股
- Price
- Shares Outstanding
- Net Income
- Book Value
- Free Cash Flow

#### A股
- 收盘价
- 总股本 / 自由流通股本
- 归母净利润
- 归母净资产
- 自由现金流（经营现金流 - 资本开支）

### 6.5 初版使用的估值指标

1. **Trailing PE**（主指标）
2. **Price / Book**（辅助，适合金融和部分资产型行业）
3. **FCF Yield**（辅助，适合成熟现金牛）

> 不建议初版使用复杂 DCF 作主判断。

---

## 7. Hold / Monitor（持有与监控层）

> 原书强调少做决策、长期持有优秀企业，因此系统不应只有“买入筛选”，还应有“继续持有 / 重新评估 / 卖出”的监控规则。

### 7.1 持有状态

| 状态 | 含义 |
|---|---|
| Buy Candidate | 通过硬过滤 + 质量高 + 估值通过 |
| Hold | 质量未变差，估值未极端化 |
| Recheck | 质量或估值出现轻微恶化 |
| Exit Candidate | 护城河/回报/风险结构恶化 |

---

### 7.2 触发再检查的条件

1. `avg_roce_5y` 显著下滑
2. 毛利率或营业利润率连续 2 年下行
3. 股本稀释加速
4. 大额并购导致商誉显著抬升
5. 估值远超合理区间

### 7.3 触发退出候选的条件

1. 长期资本回报跌破核心门槛并具持续性
2. 护城河被破坏（利润率/现金流质量/竞争地位明显恶化）
3. 财务脆弱性显著上升
4. 管理层资本配置明显转坏

---

## 8. 双市场字段映射

## 8.1 美股字段映射（建议主源：SEC XBRL）

| 逻辑字段 | 常用 XBRL / 财务概念 |
|---|---|
| Revenue | Revenues / SalesRevenueNet |
| Gross Profit | GrossProfit |
| Operating Income / EBIT | OperatingIncomeLoss |
| Net Income | NetIncomeLoss |
| Cash From Operations | NetCashProvidedByUsedInOperatingActivities |
| Capex | PaymentsToAcquirePropertyPlantAndEquipment |
| Total Assets | Assets |
| Current Liabilities | LiabilitiesCurrent |
| Current Assets | AssetsCurrent |
| Cash | CashAndCashEquivalentsAtCarryingValue |
| Debt | LongTermDebt + ShortTermBorrowings |
| Shares Outstanding | CommonStockSharesOutstanding |
| Interest Expense | InterestExpenseAndOther |
| Goodwill | Goodwill |
| Intangibles | FiniteLivedIntangibleAssetsNet |

---

## 8.2 A股字段映射（建议主源：交易所/巨潮 + 商业库；原型可 AkShare）

| 逻辑字段 | A股财报字段 |
|---|---|
| Revenue | 营业总收入 / 营业收入 |
| Gross Profit | 营业收入 - 营业成本 |
| Operating Income / EBIT近似 | 营业利润，必要时加回利息费用修正 |
| Net Income | 归属于母公司股东的净利润 |
| Cash From Operations | 经营活动产生的现金流量净额 |
| Capex | 购建固定资产、无形资产和其他长期资产支付的现金 |
| Total Assets | 资产总计 |
| Current Liabilities | 流动负债合计 |
| Current Assets | 流动资产合计 |
| Cash | 货币资金 |
| Debt | 短期借款 + 一年内到期非流动负债 + 长期借款 + 应付债券 |
| Shares Outstanding | 总股本 / 期末普通股股本 |
| Interest Expense | 财务费用拆分或附注口径 |
| Goodwill | 商誉 |
| Intangibles | 无形资产 |

---

## 9. 研发伪代码

## 9.1 单股票评分流程

```python
if avg_roce_5y < 0.20:
    reject("Low historical ROCE")

if interest_coverage is not None and interest_coverage < 3:
    reject("Weak balance sheet")

if current_ratio < 1 and current_ratio_trend_down_2y:
    reject("Weak liquidity")

if ocf_to_net_income < 0.7 for 2 consecutive years:
    reject("Poor earnings quality")

quality_score = (
    score_roce_level
    + score_roce_stability
    + score_cash_conversion
    + score_margin_stability
    + score_revenue_continuity
    + score_incremental_roce
    + score_dilution
    + score_capital_allocation
)

quality_tier = map_quality_tier(quality_score, avg_roce_10y)

valuation_pass = fair_price_gate(
    quality_tier=quality_tier,
    trailing_pe=trailing_pe,
    pb=pb,
    fcf_yield=fcf_yield,
)

if not valuation_pass:
    output_status = "Watchlist"
else:
    output_status = "Buy Candidate"
```

---

## 10. 输出设计

## 10.1 输出不应只给一个总分

推荐输出四层结果：

1. **Eligibility**：是否通过硬过滤
2. **Quality Score**：质量分
3. **Valuation Status**：估值状态
4. **Decision Status**：候选、观察、持有、复核、退出候选

---

## 10.2 单只股票详情页输出

### 顶部摘要
- 股票名称 / 代码 / 市场
- 当前状态：Buy Candidate / Watchlist / Hold / Recheck / Exit Candidate
- 质量分：0–100
- 当前估值状态：Cheap / Fair / Rich / Too Expensive

### 方法论卡片
- 过去 10 年平均 ROCE
- 过去 5 年现金转化率
- 毛利率/营业利润率稳定性
- 股本是否被稀释
- 当前 trailing PE 与适用闸门比较

### 解释层
- 为什么通过
- 为什么未通过
- 最核心的三条证据

示例：

```text
通过原因：
1. 过去 10 年平均 ROCE 为 31.4%，显著高于 20%门槛
2. 过去 5 年经营现金流 / EBIT 为 0.92，利润质量高
3. 当前 trailing PE 为 17.8x，低于该质量层允许区间 18x

风险提示：
1. 最近 2 年股本年化增速为 2.8%，接近稀释警戒线
2. 商誉占净资产比例上升，需要跟踪并购后回报
```

---

## 11. 与现有 30 因子模型的替换关系

| 现有模块 | 是否保留 | 替换建议 |
|---|---|---|
| 生存力 | 部分保留 | 改为 Hard Reject Filters |
| 复制力 | 重构 | 并入 Quality Engine 中的高回报+稳定性 |
| 适应力 | 暂弱化 | 原书不主张重预测，先不做高权重 |
| 优势积累 | 保留核心 | 用利润率/回报/连续性近似表达 |
| 估值纪律 | 重构 | 改为 Fair Price Gate |

### 11.1 应删除或降级的现有项

1. 过多基于短期价格波动的因子
2. 过多把“低估值”机械等同于“高分”的因子
3. 过多只看单年度而不看 5–10 年历史的因子

### 11.2 应保留的现有数据基础

1. fact 表：继续作为核心
2. market_bar：仅用于估值与回测，不做核心质量判断
3. available_date：必须保留，用于防前视偏差

---

## 12. 数据源建议（生产级）

## 12.1 美股

### 主源
1. SEC EDGAR XBRL
2. 公司 10-K / 10-Q 原文

### 辅助源
1. Polygon / Alpha Vantage / Tiingo / Nasdaq 行情
2. 公司投资者关系页面

### 原型级
1. yfinance（可保留原型用途，不建议唯一生产主源）

---

## 12.2 A股

### 主源（推荐生产）
1. 巨潮资讯 / 上交所 / 深交所披露文件
2. Wind / 同花顺 iFinD / Choice 之一（若预算允许）

### 原型级
1. AkShare
2. 东方财富公开接口（需注意稳定性和合规性）

---

## 13. 本阶段结论

### 13.1 必须落地的核心变化

1. 用 **长期 ROCE > 20%** 取代现有“大量普通质量因子”中的核心地位
2. 把“估值”从总分项改成 **买入闸门**
3. 把“低风险、低脆弱性”前置为 **一票否决层**
4. 把输出从“一个综合分”改成“过滤 + 质量 + 估值 + 状态”四层

### 13.2 暂不建议过度引入的内容

1. 复杂 NLP 前瞻预测因子
2. 频繁随新闻调分
3. 复杂 DCF 估值主导的决策

---

## 14. 下一阶段建议（Part 4）

下一阶段建议继续输出：

1. **章节级映射**：逐章把书中内容映射到 PRD 的哪个模块
2. **双市场回测验证方案**：如何验证新模型优于旧模型
3. **字段字典**：每个字段的数据表结构、更新频率、异常处理规则
4. **UI 输出原型说明**：如何在前端展示“Darwin 方法论解释层”

---

## 15. 一句话总结

新模型不应再是“财报数据上的多因子打分器”，而应是：

> **先排除不能长期生存和复利的企业，再用历史资本回报、护城河稳定性和合理价格去筛选少数值得长期持有的公司。**

这更接近原书的思想，也更适合作为 Darwen 的方法论护城河。
