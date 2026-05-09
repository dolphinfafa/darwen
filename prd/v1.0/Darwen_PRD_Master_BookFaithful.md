# Darwen 新版评分模型总 PRD（Master Document）

本文件汇总了基于 *What I Learned About Investing from Darwin* 对 Darwen 现有模型进行重构的四个阶段文档。

使用说明：

- 本总文档优先追求**忠实还原原书思想**，并明确区分“原书明确规则”与“产品化补充规则”。
- 目标是替换现有的 30 因子加权总分模型，改为更贴近原书的流程化模型：**硬过滤 → 质量识别 → 估值闸门 → 低频持有与监控**。
- 适用范围：产品、研发、数据、投研。

---

## 文档目录

1. Part 1：基于原书的方法论重构
2. Part 2：替代算法与数据源设计
3. Part 3：字段级算法、会计口径映射与研发实现
4. Part 4：原书逐章还原到产品规则

---


# Part 1：基于原书的方法论重构

# Darwen 新版评分模型 PRD（Part 1：基于《What I Learned About Investing from Darwin》的方法论重构）

## 文档说明

本文件是对现有 Darwen 评分模型的**第一阶段重构 PRD**。目标不是在此阶段直接给出所有代码实现细节，而是：

1. **尽可能忠实还原** Pulak Prasad 在 *What I Learned About Investing from Darwin* 一书中的投资思想；
2. 识别书中可以直接量化、可以规则化、可以产品化的内容；
3. 明确哪些规则有**清晰数字阈值**，哪些只是**原则**而不是硬阈值；
4. 为下一阶段的“算法化、因子化、数据源化”提供准确基础。

---

## 1. 重构目标

当前 Darwen 模型更接近“高质量基本面量化筛选器”。  
而这本书的核心并不只是筛“财务好”的公司，而是筛：

- **先避开大风险**
- **再买高质量**
- **价格必须合理**
- **极少交易**
- **长期持有**
- **永远优先使用历史事实，而不是预测**

因此，新版模型需要从“财务指标综合打分”升级为：

> **Darwin Process Model（达尔文式投资流程模型）**
>
> 先做严格排除，再做质量筛选，再做价格约束，最后进入长期持有名单。

---

## 2. 这本书中最重要的投资主张（按优先级排序）

### 2.1 第一原则：先避免重大永久性亏损，而不是先追求收益

这是全书最重要的原则。作者明确强调：

- 生物首先追求生存；
- 投资也应先避免重大损失；
- 允许错过机会，但不接受高概率永久性损失。

### 2.2 第二原则：投资的关键不在“会选”，而在“会拒绝”

作者的核心表述可以概括为：

> 我们只有先成为更好的 rejector（拒绝者），才有机会成为更好的 investor（投资者）。

### 2.3 第三原则：高质量企业的最佳单一初筛指标是“历史 ROCE”

作者给出了非常明确的数值门槛：

- **长期历史 ROCE 低于 20% 的企业，直接排除**
- 作者用于初筛的公司池，只包含：
  - **过去 5–10 年或更长时间里，ROCE 超过 20% 的公司**

这部分是书里最适合直接落地为硬规则的内容之一。

### 2.4 第四原则：只看历史事实，不做预测

书中反复强调：

- 不做 DCF 驱动的未来预测；
- 不依赖 forward PE；
- 不听管理层故事；
- 不根据“明年会更好”建模；
- 只用过去已发生、可验证、公开可获得的数据。

### 2.5 第五原则：高质量企业必须具备“稳健性/鲁棒性（robustness）”

作者认为高质量企业不只是 ROCE 高，还应同时具备：

- 低债务或无债务
- 强竞争优势
- 客户分散
- 供应商分散
- 管理层稳定
- 所处行业变化慢

### 2.6 第六原则：估值重要，但作者并没有给出一个统一的“绝对 PE 上限”

这是一个必须明确写进 PRD 的事实：

- 书里**没有给出统一的、适用于所有公司的一刀切买入 PE 上限**；
- 作者明确强调**价格敏感**，但不是“PE 超过某个固定数字一律不买”。

能确认的数字包括：

- **市场长期 PE 大约为 19–20 倍**
- 作者组合在买入时的**中位 trailing PE 为 14.9 倍**
- 在金融危机期间买入 Page Industries 时，作者给出的买入 **TTM PE 为 18 倍**
- 书中讨论“为什么继续持有 60 PE”的问题，明确表示：
  - **高估值时不会新买**
  - 但**不会仅因估值高而卖出好公司**

因此，产品层面必须避免“伪忠实”地写成：

> “PE > X 一律不投”

如果书中没有这个统一 X，就不能强行造一个。

### 2.7 第七原则：不因估值高而卖出高质量企业

作者在后半部分非常明确：

- **买入时价格敏感**
- **持有时不因估值高而卖出**
- **真正卖出的原因是：**
  - 糟糕且严重的资本配置错误
  - 业务出现不可逆破坏

### 2.8 第八原则：市场短期波动大多是“proximate cause（近因）”，不应主导决策

作者区分：

- **proximate cause（近因）**：宏观、政策、短期行业新闻、情绪、突发 headlines
- **ultimate cause（终因）**：企业长期成功或失败的根本经营质量

结论：

- 不用短期新闻改变核心评分；
- 可以把重大事件作为“风险标签层”，但不应轻易覆盖企业长期质量判断。

### 2.9 第九原则：只信“诚实信号（honest signals）”，不信“便宜信号（cheap signals）”

作者明确不依赖以下输入：

- 管理层访谈
- 路演表达
- 业绩指引
- PR 文案
- 宏大愿景叙事

作者更信任的信号：

- 历史财务表现
- 可验证的竞争地位
- 客户/供应商/前员工/同行反馈
- 可持续的自由现金流和资本回报

### 2.10 第十原则：不是投资单个公司，而是投资“重复出现的成功模板”

作者将其称为“convergence / outside view”。

产品化含义：

- 新版模型不能只看单个公司本身；
- 还应看它是否属于“历史上反复成功的一类公司”。

---

## 3. 书中可以直接提炼为硬规则的内容

以下内容可以直接进入新版评分/筛选引擎：

### 3.1 可直接作为硬过滤器的规则

#### Rule A：排除长期 ROCE < 20% 的公司
- 依据：作者明确写到，经过风险过滤后，**长期历史 ROCE 低于 20% 的企业直接排除**
- 窗口：**5–10 年或更长**
- 建议实现：
  - `avg_roce_5y >= 20%`
  - `avg_roce_10y >= 20%`（优先）
  - 若上市时间不足 10 年，则退化为 5 年

#### Rule B：排除高杠杆企业
- 书中未给出统一的精确数值，如 “Debt/Equity > X”
- 但作者多次明确表达：
  - 尽可能远离 leverage
  - 更偏好 **zero debt / minimal debt**
- 产品化方式：
  - 不写死作者未明确写出的阈值为“原书规则”
  - 可以在工程实现层做：
    - `net_debt <= 0` 记为最优
    - `net_debt / EBITDA` 分档
    - `interest_coverage` 分档
- 但文案上必须写明：
  - **这是产品为还原“detesting debt”而做的工程映射，不是作者给出的显式数值门槛**

#### Rule C：排除 turnarounds（困境反转型公司）
- 作者明确表示不喜欢 turnaround
- 典型表现：
  - 长期低 ROCE
  - 最近两年故事变好但历史很差
  - 靠重组/M&A/换管理层讲反转逻辑
- 可产品化为：
  - 历史 5–10 年盈利能力差
  - 历史 FCF 质量差
  - 最近 1–2 年突然改善但长期均值仍差
  - 进入“turnaround suspicion”标签并默认排除

#### Rule D：排除 serial acquirers（并购成瘾者）
- 作者明确写到会远离 M&A addicts
- 可产品化观察指标：
  - 高频大额并购
  - goodwill / intangible 占比长期上升
  - 股本摊薄持续上升
  - 依赖并购而非内生增长
- 这一条需要进入新版模型

#### Rule E：排除 fast-changing industries（变化太快的行业）
- 作者明确表示自己无法理解快变行业，因此主动回避
- 这不是“行业评分低”，而是“能力圈外排除”
- 产品化：
  - 先按市场定义“快变行业清单”
  - 默认降低可投资等级或直接列入禁投池
- 对美股/A股应分别定义

#### Rule F：排除 government-owned enterprise（国有控股/政府目标多元企业）
- 作者有非常明确的表达：
  - **政府拥有的企业，他“不论什么价格都不投”**
- 这是书里少数接近“at any price”的硬规则
- 对 A 股市场尤其重要，应设为独立过滤器

#### Rule G：排除 unaligned owners（利益不一致的控制权结构）
- 作者偏好：
  - 创始人/企业家主导
  - 创始人通常是最大股东
  - 自己往往是第二大股东
- 这意味着新版模型应增加：
  - 控股股东结构
  - 创始人持股
  - 管理层与股东利益一致性

---

## 4. 书中可提炼为“质量维度”的内容

作者的“高质量”不是单维度，而是多层鲁棒性。新版模型建议将质量拆成 5 个大模块。

### 4.1 模块 Q1：Capital Efficiency（资本效率）
这是最接近作者“单一最佳初筛指标”的维度。

核心要点：
- 重点看历史 ROCE
- 不看“未来会变高”
- 只看已实现的 ROCE

建议指标：
- `avg_roce_10y`
- `median_roce_10y`
- `min_roce_10y`
- `roce_std_10y`
- `roce_positive_year_ratio`

### 4.2 模块 Q2：Balance Sheet Robustness（资产负债表稳健性）
核心思想：
- 少债或无债
- 高质量企业在危机中不需要向市场求救

建议指标：
- `net_cash_or_net_debt`
- `interest_coverage`
- `debt_to_equity`
- `debt_to_ebitda`
- `equity_dilution_5y`

### 4.3 模块 Q3：Business Robustness（经营稳健性）
作者列出的 robust business 特征包括：
- 客户分散
- 供应商分散
- 竞争优势强
- 管理层稳定
- 行业变化慢

建议指标：
- `customer_concentration`
- `supplier_concentration`
- `management_turnover`
- `industry_change_speed`
- `gross_margin_stability`
- `fcf_conversion_consistency`

### 4.4 模块 Q4：Honest Signals（诚实信号）
核心思想：
- 只信“成本高、不可伪造”的信号
- 不信管理层故事和 forward guidance

建议指标：
- `historical_margin_consistency`
- `historical_fcf_positive_ratio`
- `historical_product_launch_frequency`（若可得）
- `historical_market_share_trend`（若可得）
- `forensic_red_flags`

### 4.5 模块 Q5：Template Fit（成功模板匹配度）
这是当前 Darwen 雏形中最欠缺、但最接近本书思想的部分。

问题不是：
- “这家公司看起来好不好？”

而是：
- “它是否属于历史上反复成功的一类公司？”

建议模板特征：
- 高 ROCE
- 内生增长为主
- 聚焦而非分散
- 创始人/企业家文化
- 低杠杆
- 高 FCF
- 竞争壁垒清晰
- 行业变化速度慢

---

## 5. 书中的价格/估值思想，如何准确还原

### 5.1 确认存在的数字

以下数字在书里可以明确确认：

1. **长期市场 PE 大约 19–20 倍**
2. **作者买入时组合中位 trailing PE = 14.9 倍**
3. **2008/09 买入 Page 时 TTM PE = 18 倍**
4. 书中举例说明：
   - 某优质公司可能从 **15x PE 扩张到 60x PE**
   - 即便到 **60x PE**，若业务继续成长，也**不因为估值高而卖出**

### 5.2 不能伪造的部分

书里**没有**看到作者给出以下硬阈值：
- `PE > 30 不投`
- `PE > 40 不投`
- `PB > 5 不投`

因此在新版 PRD 中，必须明确：

> 估值模块不能假装成“Pulak Prasad 的精确硬阈值模型”，除非该数字在原书里明确出现并被定义为规则。

### 5.3 正确的产品化方式

估值模块应采用两层结构：

#### 层 1：原书忠实层
- 使用 trailing valuation，而不是 forward valuation
- 强调对买入价格敏感
- 使用历史已实现盈利，而不是预测盈利
- 使用市场长周期估值中枢作为参考（如 19–20x）

#### 层 2：工程实现层
为便于量化，可加入：
- trailing PE 相对自身历史分位
- trailing PE 相对市场中枢偏离
- trailing EV/EBITDA 相对历史分位
- trailing FCF yield
- normalized earnings yield

但产品说明必须注明：
- 这些是“对原书 price sensitive 原则的工程映射”
- 不是作者书中的逐字阈值

---

## 6. 对现有 Darwen 模型的主要替换建议

### 6.1 从“加总打分”改为“分层漏斗”
当前模型偏像 30 因子加权总分。  
建议替换为四层：

#### Layer 1：Hard Reject Filters（硬排除）
先排除：
- 长期 ROCE 不达标
- 高债
- turnarounds
- serial acquirers
- fast-changing industries
- government-owned enterprises
- owner alignment 差

#### Layer 2：Quality Score（质量评分）
只对通过硬过滤的公司评分。

#### Layer 3：Valuation Gate（估值闸门）
估值不合理则不进入可买池。

#### Layer 4：Hold Forever Monitoring（长期持有监控）
买入后不因估值高卖出，只监控：
- 资本配置恶化
- 业务不可逆破坏
- 治理崩塌

### 6.2 从“预测因子”改为“历史事实因子”
现有模型中任何以下内容都应降权或移除：
- forward growth
- analyst estimate
- 管理层指引
- 主题热度
- 短期新闻情绪直接改分

### 6.3 从“事件即改分”改为“事件打标签”
本书思想不支持因为短期新闻就重写核心质量分。  
因此：
- 新闻舆情系统应默认进入 `event_risk_layer`
- 不直接覆盖核心 Darwin Quality Score
- 除非事件证实了长期质量被破坏（如重大造假、连续大额并购失控、资本配置明显恶化）

---

## 7. 第一阶段可确认的“作者原话级规则”与“工程映射规则”区分

### 7.1 作者原话级规则（可直接作为产品卖点）
- 永久持有高质量企业
- 先避风险再谈收益
- 宁可错过，不可永久亏损
- 不碰 crooks
- 不碰 turnarounds
- 尽量远离 leverage
- 不碰 M&A addicts
- 不碰 fast-changing industries
- 不碰利益不一致的 owner structure
- 不碰政府控股企业（作者对这点非常绝对）
- 初筛只看历史 ROCE
- 长期 ROCE 低于 20% 排除
- 不做预测，不做 forward PE 驱动决策
- 买入时看价格，持有后不因估值高卖出

### 7.2 工程映射规则（必须注明是产品化推导）
- 用 `debt_to_ebitda`、`interest_coverage` 表达“detesting debt”
- 用 `goodwill/assets`、`M&A frequency` 表达“serial acquirer”
- 用 `industry volatility / innovation speed` 表达“fast-changing industries`
- 用 `founder_ownership / promoter_holdings` 表达 owner alignment
- 用 `historical valuation percentile` 表达 fair price

---

## 8. 当前阶段的结论

基于本书，Darwen 新版模型最关键的变化不是“再多接几个数据源”，而是：

### 8.1 先把模型哲学改对
从：
- 财务+行情综合打分器

改成：
- **Darwin 式排除-筛选-估值-长期持有流程**

### 8.2 先把“硬排除”建起来
这是当前系统与原书差距最大的地方。

### 8.3 估值必须忠实表达“不乱造阈值”
可以做估值约束，但不能虚构一个作者未写过的 PE 上限。

---

## 9. 下一阶段（Part 2）将输出的内容

下一段 PRD 将继续完成：

1. **把本书原则映射成完整算法结构**
2. **替换现有 30 因子体系**
3. **定义每个模块的评分公式**
4. **区分美股/A股的数据口径**
5. **给出可靠数据源优先级**
6. **设计输出页和解释页**
7. **说明哪些维度需要新增文本/治理/股权结构数据**

---

## 10. 当前阶段给产品和研发的执行指令

在 Part 2 之前，研发侧可先做以下准备：

1. 在现有模型中新增 `hard_reject_reason` 字段
2. 将当前模型拆成：
   - `reject_filters`
   - `quality_score`
   - `valuation_gate`
   - `hold_monitor`
3. 从现在开始，任何“作者阈值”都必须标记为：
   - `book_explicit_threshold`
   - 或 `engineered_proxy_threshold`
4. 估值页必须区分：
   - trailing valuation
   - forward valuation（仅展示，不参与核心 Darwin 决策）

---

## 附：本阶段最关键的明确数字

| 项目 | 数值 | 说明 |
|---|---:|---|
| 长期历史 ROCE 初筛下限 | 20% | 书中明确给出 |
| ROCE 观察窗口 | 5–10 年或更长 | 书中明确给出 |
| 长期市场 PE 中枢 | 19–20x | 书中明确给出 |
| 作者买入时组合中位 trailing PE | 14.9x | 书中明确给出 |
| Page 金融危机买入 TTM PE | 18x | 书中明确给出 |
| 持有讨论中的高估值示例 | 60x PE | 书中用于说明“高估值不必然卖出” |

---

## 附：必须诚实披露的事项

- 书中**没有统一的绝对 PE 买入上限**；
- 书中**没有统一的 debt ratio 硬阈值**；
- 书中**没有统一的 PB/EVEBITDA 硬阈值**；
- 这些若要在产品中出现，必须明确标注为**工程映射**，而不是“原书明文规则”。

---

# Part 2：替代算法与数据源设计

# Darwen PRD Part 2  
## 基于《What I Learned About Investing from Darwin》的替代算法与数据源设计（双市场版）

> 本文是 Part 1 的继续，目标不是“优化现有 30 因子模型”，而是**按原书思想重构评分引擎**。  
> 核心原则：**先排除大风险，再识别高质量，再判断价格是否合理，最后用极低频持有纪律收获复利。**

---

## 1. 文档目标

### 1.1 背景
现有模型以 30 个财务因子加权求总分为主，虽然可运行，但更接近“基本面量化质量模型”。  
而原书的方法并不是“多因子平均加权”，而是更接近四层结构：

1. **Avoid Big Risks**：先排除可能永久损失本金的对象
2. **Buy High Quality at a Fair Price**：在剩余股票中找高质量企业
3. **Valuation as Gate, not Forecast**：估值用于控制买入纪律，不依赖 DCF 和远期预测
4. **Don’t Be Lazy—Be Very Lazy**：买入后低换手、低干预、长期持有

### 1.2 本阶段目标
将 Darwen 的核心模型替换为以下新结构：

- **Layer A：硬性排除层（Hard Reject Filters）**
- **Layer B：质量识别层（Quality Engine）**
- **Layer C：合理价格闸门（Fair Price Gate）**
- **Layer D：持有与再评估层（Hold / Monitor Engine）**

---

## 2. 原书思想到系统结构的映射

| 原书思想 | 系统实现方式 | 是否作为硬规则 |
|---|---|---|
| 避免大风险比追求高收益更重要 | 先做排除，不通过则不评分 | 是 |
| 不碰 turnarounds、脆弱企业、差生意 | 风险排除层 | 是 |
| 用长期 ROCE 识别优秀商业体质 | 质量层核心主因子 | 是 |
| 高质量企业来自“强适应性 + 强鲁棒性” | 质量层拆为 ROCE、FCF、稳健性、竞争结构 | 否 |
| 不依赖 DCF 和远期预测 | 不使用 forward PE / DCF 为主评分输入 | 是 |
| 估值的作用是保护自己，而不是精确预测 | 估值只做买入闸门和仓位调节 | 是 |
| 真正的复利来自长期持有极少数好公司 | 低频调仓、卖出条件更严 | 是 |

---

## 3. 新模型总架构

```text
股票池
  ↓
Layer A: Hard Reject Filters（大风险排除）
  ↓
合格股票池
  ↓
Layer B: Quality Engine（商业质量评分）
  ↓
Layer C: Fair Price Gate（估值闸门）
  ↓
Buy / Watch / Reject
  ↓
Layer D: Hold / Monitor（长期持有与低频复核）
```

---

## 4. Layer A：硬性排除层（Hard Reject Filters）

这一层是本次替换的核心。原书不是“每个因素加点分再平均”，而是**先大量淘汰**。  
任何股票只要命中以下任一规则，直接进入 `Reject`，不进入后续评分。

### 4.1 A1：长期 ROCE 不达标

#### 原书依据
作者明确写到：  
- **长期历史 ROCE 低于 20% 的公司直接排除**  
- 预筛后的短名单由**过去 5–10 年或更长时间 ROCE > 20%** 的公司构成

#### 产品规则
- 取最近 **5 年、8 年、10 年** 三个窗口
- 计算年化/逐年 ROCE 轨迹
- 满足以下任一条件则排除：
  - 5Y 平均 ROCE < 20%
  - 8Y 平均 ROCE < 20%
  - 10Y 平均 ROCE < 20%（如数据不足可缺省）
  - 最近 5 年中有 3 年以上 ROCE < 15%

#### 说明
这里不建议只看单年 ROCE，否则会被周期性或一次性利润扭曲。  
本规则是整个系统最接近原书硬门槛的部分。

#### 公式
```text
ROCE = EBIT / Capital Employed
Capital Employed = Net Fixed Assets + Working Capital
Working Capital = Inventory + Receivables - Payables
```

> 对金融股、保险、券商不适用，默认从股票池排除，后续如要支持须建立单独模型。

---

### 4.2 A2：持续自由现金流能力不足

#### 原书对应思想
作者反复强调：真正好的企业不仅盈利好，而且在增长后仍能不断释放自由现金流。  
高收入增长但长期不产生 FCF，不应被视为优秀商业模式。

#### 产品规则
最近 5 年若满足以下任一条件则排除：
- 5Y FCF 累计 <= 0
- 5Y 中有 4 年以上 FCF 为负
- 经营现金流/净利润（OCF/NI）5Y 平均 < 0.8

#### 公式
```text
FCF = Operating Cash Flow - Capex
Cash Conversion = OCF / Net Income
```

---

### 4.3 A3：资产负债表脆弱

#### 原书对应思想
Section I 的核心是避免永久性损失，脆弱资产负债表是大风险来源之一。

#### 产品规则
满足以下任一条件则排除：
- Interest Coverage < 3（近 3 年任一年）
- Net Debt / EBIT > 3（近 3 年任一年）
- Current Ratio < 1 且连续 2 年恶化
- OCF 连续 3 年为负

#### 市场差异
- 美股：利息支出、总债务、现金可直接从 SEC XBRL 拿
- A股：部分公司利息支出披露颗粒度不稳定，需优先用公告报表；若缺失，则降级为 Net Debt / EBITDA 或资产负债率替代

---

### 4.4 A4：Turnaround / 弱商业体质行业

#### 原书对应思想
作者明确对 turnaround 抱有高度警惕。  
如果一家企业要靠“管理层神奇逆转”才能成立，通常不属于想要的标的。

#### 产品规则
以下情形进入 `Reject`：
- 最近 5 年有 2 年以上 ROCE < 10%，但当前突然单年反弹
- 最近 5 年有 2 年以上经营利润为负
- 过去 5 年依赖大规模再融资、定增、发债输血维持经营
- 行业被标记为“高周期 + 高资本开支 + 低议价权”且企业 ROCE 不稳定

#### 行业初始排除名单（默认）
- 航空
- 航运
- 钢铁
- 水泥
- 大宗商品采掘
- 通用地产开发
- 强周期面板/化工子行业
- 金融企业（单独模型前排除）

> 这不是说这些行业不能赚钱，而是它们通常不符合本书“高确定性复利生物”的选股框架。

---

### 4.5 A5：财务质量异常 / 会计信号差

#### 产品规则
满足任一条件则排除：
- 5Y 平均应收增速明显高于收入增速（阈值：高出 > 15pct）
- 5Y 平均存货增速明显高于收入增速（阈值：高出 > 15pct）
- OCF/EBIT 连续 3 年 < 0.7
- 股本摊薄 5Y 累计 > 20% 且无明确并购逻辑

#### 说明
原书并不主张复杂会计模型，但其“避免大风险”非常适合加入简单明确的财务质量红旗。

---

## 5. Layer B：质量识别层（Quality Engine）

通过 Layer A 后，系统不再用“30 因子平权”，而是围绕**鲁棒性（robustness）+ 可演化性（evolvability）**来识别真正的高质量企业。

总分范围：0–100 分。  
仅由 4 个一级维度组成，避免过度复杂化。

| 一级维度 | 权重 | 对应原书思想 |
|---|---:|---|
| Q1 资本效率与现金复利 | 35% | ROCE、FCF、资本配置 |
| Q2 商业模式鲁棒性 | 30% | 强生意、低脆弱性、好行业位置 |
| Q3 演化能力代理变量 | 20% | 适应性不能直接测，但可通过鲁棒性与持续改善间接测 |
| Q4 管理与治理克制性 | 15% | 不迷信管理层访谈，但用行为数据看治理质量 |

---

### 5.1 Q1：资本效率与现金复利（35分）

#### 因子 Q1-1：长期 ROCE 水平（15分）
- 10Y / 8Y / 5Y 平均 ROCE
- 评分：
  - ≥ 35%：15分
  - 30–35%：13分
  - 25–30%：10分
  - 20–25%：7分
  - < 20%：前层已淘汰

#### 因子 Q1-2：ROCE 稳定性（8分）
- 近 5 年 ROCE 标准差越低越好
- 近 5 年最低 ROCE 若仍 > 20%，加分

#### 因子 Q1-3：FCF 质量（7分）
- 5Y FCF / EBIT
- 5Y FCF Margin
- FCF 连续为正的年数

#### 因子 Q1-4：资本配置纪律（5分）
- 分红 + 回购是否在不牺牲增长和现金安全下进行
- 若持续增发融资且 ROCE 无改善，则扣分

---

### 5.2 Q2：商业模式鲁棒性（30分）

#### 因子 Q2-1：毛利率与营业利润率稳定性（8分）
- 5Y 毛利率波动低
- 5Y EBIT Margin 波动低

#### 因子 Q2-2：营运资本优势（8分）
原书偏爱有议价权、资金占用少、甚至能形成“负营运资本”的企业。

- 应收天数越低越好
- 存货天数越低越好
- 应付天数相对更长加分
- CCC（现金转换周期）越短越好

#### 因子 Q2-3：收入增长的“健康性”而非速度（8分）
- 不追求极高增长
- 关注 5Y Revenue CAGR 的平稳程度
- 增长显著高于 ROCE 时未必加分，因为可能侵蚀 FCF

#### 因子 Q2-4：反脆弱性代理（6分）
- 在市场压力期 / 宏观冲击期，利润率和现金流是否仍相对稳
- 可用 2008、2020、2022 等冲击窗口做横截面表现回溯
- 若回撤期盈利质量仍显著好于行业中位数，加分

---

### 5.3 Q3：演化能力代理变量（20分）

> 原书认为“适应性”难以直接预测，因此不建议依赖管理层访谈和主观故事。  
> 系统上不把“未来创新想象空间”作为直接评分项，而用**过去多年持续改善的痕迹**作为代理。

#### 因子 Q3-1：盈利能力改善轨迹（8分）
- 5Y 毛利率趋势
- 5Y EBIT Margin 趋势
- 5Y ROCE 趋势

若三者中两项以上显著上升，说明企业在强化系统能力。

#### 因子 Q3-2：现金流改善轨迹（6分）
- OCF/NI 趋势
- FCF Margin 趋势

#### 因子 Q3-3：资本轻化或效率提升（6分）
- Revenue / Capital Employed 趋势
- Capex / Revenue 趋势

---

### 5.4 Q4：管理与治理克制性（15分）

> 原书对 management meetings 很怀疑，因此这里不把“管理层故事”作为主要依据，而用可验证行为数据。

#### 因子 Q4-1：股东友好且克制（6分）
- 持续大额价值毁灭型并购扣分
- 在高估值时期频繁增发扣分
- 稳定分红但不透支现金流加分

#### 因子 Q4-2：治理稳定性（5分）
- 近 5 年 CEO/CFO 频繁更换扣分
- 审计意见非标扣分
- 重大处罚 / 内控缺陷扣分

#### 因子 Q4-3：会计诚实度（4分）
- OCF 与利润长期背离扣分
- 重大重述、频繁非经常性损益美化扣分

---

## 6. Layer C：合理价格闸门（Fair Price Gate）

这层不对“好公司质量”重新打分，而是决定：
- 是否可以买
- 什么时候可以买
- 是否应降权等待

### 6.1 原书落地原则
书里给出的关键信息有三点：

1. **不依赖 DCF**
2. **不以 forward PE 为主要判断依据**
3. **Nalanda 组合历史买入中位 TTM PE 为 14.9x**
4. **Page 买入时 TTM PE 为 18x**
5. **市场长期中枢（例：Sensex）约 19.7x**

因此，产品不应做成“PE 超过 X 就 reject”的机械模型，而应做成**估值闸门 + 质量联动**。

---

### 6.2 估值使用原则

#### 原则 1：只使用 TTM / 历史兑现口径
禁止将以下数据作为主买入依据：
- Forward PE
- 两年后一致预期利润
- DCF 单点估值

#### 原则 2：用“相对历史 + 相对质量 + 相对市场”判断 fair price
估值必须同时参考：
- 公司自身历史估值分位
- 市场/行业估值中枢
- 企业质量等级

---

### 6.3 Fair Price Gate 规则

#### 分类输出
- `BUY`
- `WATCH`
- `TOO EXPENSIVE`

#### 输入因子
- TTM PE
- PB（仅作辅助）
- FCF Yield
- EV/EBIT（资本结构修正）
- 公司过去 10Y 自身估值分位
- 所在市场长期 PE 中枢

#### 规则设计

##### C1：绝对估值状态
按 TTM PE 分类：

- ≤ 15x：强通过
- 15–18x：通过
- 18–22x：观察
- 22–28x：谨慎，仅顶级质量企业可观察
- > 28x：默认过贵，除非进入“例外观察名单”
- > 35x：默认 `TOO EXPENSIVE`

> 注意：这里的 15x/18x 是根据书中的 14.9x 和 18x 买入案例外推得到的产品阈值，不是原书逐字硬规则。  
> 原书明确数字只有 14.9x、18x、市场约 19.7x；因此产品内要把这些阈值标记为“系统化实现阈值”，不能宣称为作者原文规则。

##### C2：相对历史估值分位
- 公司当前 TTM PE 低于自身 10Y 分位数 40%：加一档
- 高于 80%：降一档

##### C3：质量-估值联动
只有当 `Quality Score >= 85` 时，才允许进入高估值观察区：
- PE 22–28x：可列入 WATCH
- PE > 28x：不可买，只观察

##### C4：安全边际
如果当前价格相对 52 周高点回撤 > 25%，且质量分数不变，可从 WATCH 升到 BUY 观察名单。

---

## 7. Layer D：持有与再评估层（Hold / Monitor Engine）

原书的第三部分强调：真正的收益来自**低频、长期、尽量少做事**。  
所以系统必须支持“买入后少折腾”，而不是日频改分导致高换手。

### 7.1 复核频率
- 质量层：季度更新
- 估值层：日更或周更
- 风险红旗层：事件触发

### 7.2 卖出规则（比买入更严格）
默认只有以下情况触发卖出建议：
1. Hard Reject 条件被触发
2. 质量分数连续两个财报期显著下滑（例如跌破 70）
3. 治理/合规发生重大破坏（审计非标、监管重罚、财务造假）
4. 估值极端泡沫化（例如进入历史 >95% 分位且 TTM PE > 35x）

### 7.3 输出状态
- `BUY`
- `HOLD`
- `WATCH`
- `RED FLAG`
- `EXIT`

---

## 8. 双市场数据源设计（可靠性优先级）

本节不是“能抓到什么就用什么”，而是按**可靠性优先级**给出正式生产方案。

---

### 8.1 美股数据源

#### 一级（生产主源）
1. **SEC EDGAR / data.sec.gov**
   - 用途：
     - 10-K / 10-Q / 8-K / 20-F / 6-K
     - XBRL companyfacts
     - submissions filing history
   - 可靠性：最高
   - 适合：
     - 财报事实表
     - available_date
     - 8-K 事件流
   - 说明：
     - SEC 官方 API 提供 companyfacts、submissions，XBRL 数据实时更新，无需 API key；EDGAR 披露数据可公开抓取，并有速率要求。citeturn497110search0turn497110search7

2. **公司原始 10-K / 10-Q HTML / iXBRL**
   - 用途：补充 companyfacts 中缺失科目、拆分口径校验
   - 可靠性：最高

#### 二级（生产辅助）
3. **CRSP / FactSet / S&P Capital IQ / Bloomberg**（商业）
   - 用途：
     - 历史价格
     - 退市收益
     - Corporate Actions
     - 行业分类
   - 若预算允许，价格与总回报建议使用商业源

#### 三级（原型/低成本）
4. **yfinance**
   - 用途：历史 OHLCV、快速原型
   - 风险：
     - 官方文档明确其为开源工具，不隶属 Yahoo，数据主要面向研究和教育用途，Yahoo 数据使用也受其条款限制。citeturn308310search0turn308310search1
   - 结论：
     - 可用于 MVP，不建议作为最终生产唯一行情源

---

### 8.2 A 股数据源

#### 一级（生产主源）
1. **巨潮资讯（CNINFO）**
   - 用途：
     - 上市公司公告
     - 年报/季报 PDF/HTML
     - 风险提示、董事会决议、处罚公告
   - 可靠性：
     - 极高
   - 说明：
     - 巨潮资讯是深交所法定信息披露平台，也覆盖沪市等多板块公告聚合，是 A 股公告主源之一。citeturn497110search1turn497110search2

2. **上海证券交易所 / 深圳证券交易所官网**
   - 用途：
     - 定期报告披露
     - 交易所层面的公告与监管信息
   - 可靠性：极高
   - 说明：
     - 上交所官网提供上市公司定期报告及预约披露等官方页面；深交所公告亦可作为法定披露来源。citeturn497110search3turn497110search5

3. **公司年报/季报原文**
   - 用途：
     - 关键会计项目校验
     - 审计意见、管理层讨论、资本开支等附注数据

#### 二级（生产辅助）
4. **Wind / CSMAR / 同花顺 iFinD / Choice**（商业）
   - 用途：
     - 标准化财务数据
     - 历史复权行情
     - 行业分类
     - 机构持股
   - 若做正式产品，A 股建议至少接一套商业标准化源

#### 三级（原型/低成本）
5. **AkShare**
   - 用途：
     - A 股财务报表
     - 日线行情
     - 分红、部分基本面接口
   - 风险：
     - 文档明确提示数据使用风险，部分字段和复权行情存在异常样例。citeturn308310search2turn308310search5
   - 结论：
     - 可用于原型和研究，不建议作为唯一正式生产主源

---

## 9. 字段级取数映射

### 9.1 核心字段

| 目标字段 | 美股优先来源 | A股优先来源 | 备注 |
|---|---|---|---|
| Revenue | SEC companyfacts / 10-K | 年报/季报原文 / 商业标准化源 | 必须保留 available_date |
| EBIT / Operating Profit | SEC XBRL | 年报/季报原文 | A股需注意营业利润与 EBIT 映射 |
| Net Fixed Assets | SEC XBRL | 资产负债表 | |
| Inventory | SEC XBRL | 资产负债表 | |
| Receivables | SEC XBRL | 资产负债表 | |
| Payables | SEC XBRL | 资产负债表 | |
| OCF | SEC XBRL | 现金流量表 | |
| Capex | SEC XBRL 或现金流附表 | 现金流量表购建固定资产现金 | |
| Debt | SEC XBRL | 资产负债表 | |
| Interest Expense | SEC XBRL | 利润表/附注 | A股缺失时可降级替代 |
| Shares Outstanding | SEC submissions/companyfacts | 年报/股本变动公告 | |
| Audit Opinion | 10-K / 20-F 文本 | 年报审计意见 | |
| CEO/CFO Change | 8-K | 公告 | |
| Regulatory Action | 8-K / SEC enforcement | 交易所/证监会/公告 | |

---

## 10. 算法落地细节

### 10.1 计算顺序
```text
Step 1: Universe 构建
Step 2: 行业与证券类型过滤
Step 3: Hard Reject Filters
Step 4: Quality Score 计算
Step 5: Fair Price Gate
Step 6: 状态输出（BUY/HOLD/WATCH/EXIT）
```

### 10.2 最终状态逻辑

#### BUY
- 通过所有 Hard Reject
- Quality Score >= 80
- Fair Price Gate 通过
- 无重大红旗事件

#### HOLD
- 已持有
- Quality Score >= 75
- 无重大破坏

#### WATCH
- Quality Score 高，但估值偏贵
- 或质量合格但等待更好价格

#### EXIT
- 触发 Hard Reject
- 或重大治理/财务红旗

---

## 11. 与现有 30 因子模型的替换关系

### 11.1 删除
以下现有逻辑建议删除或降级：
- 过多短期行情因子
- 将估值与质量混在一起加总
- 用单个新闻事件立刻改总分
- 用 forward PE 或 DCF 预测作为主买入依据

### 11.2 保留并重构
- S1 杠杆 / 流动性 / FCF → 进入 Hard Reject
- ROIC/ROCE → 升级为质量主引擎核心
- 会计质量 → 保留为风险红旗
- 估值纪律 → 改为 Gate，不再参与大权重总分

### 11.3 新模型核心差异
旧模型问的是：
> “一只股票综合得多少分？”

新模型问的是：
> “这是不是一只值得长期拥有的优秀生物？如果是，现在价格是否给了我安全边际？”

---

## 12. 产品输出设计

### 12.1 单票输出
- `Status`: BUY / HOLD / WATCH / EXIT
- `Hard Reject`: Pass / Fail
- `Quality Score`: 0–100
- `Fair Price Gate`: Pass / Watch / Too Expensive
- `Key Reasons`: 3–5 条
- `Red Flags`: 事件与治理提示

### 12.2 页面模块
1. **总览卡片**
   - 状态
   - 质量分
   - 当前 TTM PE
   - 历史估值分位

2. **Hard Reject 检查卡**
   - ROCE 是否达标
   - FCF 是否达标
   - 资产负债表是否安全

3. **Quality 解释卡**
   - ROCE 历史图
   - FCF 历史图
   - CCC/利润率趋势

4. **Fair Price 卡**
   - 当前估值 vs 历史估值
   - 当前估值 vs 市场中枢
   - 是否处于作者偏好的价格区间

5. **Monitor 卡**
   - 审计意见
   - 高管变动
   - 监管/处罚事件

---

## 13. 实施优先级

### P0（立即）
- 新增 Hard Reject 层
- 重构 Quality Score
- 将估值从总分中拆出，改为 Gate

### P1
- 完成双市场字段映射
- 增加 audit opinion / management change / regulatory red flag

### P2
- 增加文本抽取（10-K/年报中的审计意见、重大诉讼、内控缺陷）
- 增加行业结构标签

---

## 14. 本阶段结论

这套替代模型与原书更一致，主要体现在四点：

1. **先排除，而不是先加权**
2. **以长期 ROCE>20% 为核心门槛**
3. **估值是闸门，不是主评分器**
4. **目标是长期持有少数优秀公司，而不是频繁择时**

---

## 15. 下一段建议（Part 3）

下一段建议继续输出以下内容：

1. **逐字段 SQL / Python 计算口径**
2. **美股 / A 股会计科目映射表**
3. **回测 PRD 的 Darwin 版重构**
4. **新闻与重大舆情到底如何接入，不破坏“非常懒惰”的核心纪律**

---

# Part 3：字段级算法、会计口径映射与研发实现

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

---

# Part 4：原书逐章还原到产品规则

# Darwen PRD Part 4：原书逐章还原 → 产品规则映射

> 文档目的：
> 1. 把《What I Learned About Investing from Darwin》逐章拆解为产品规则；
> 2. 严格区分“原书直接支持的规则”和“产品化补充规则”；
> 3. 为现有模型替换提供理论依据文档。

---

## 1. 使用原则

本文件遵循以下约束：

- **只把原书明确表达的投资思想，映射为产品规则**。
- 对于书中**没有给出统一硬阈值**的地方，不伪造数字。
- 对于产品必须落地、但书中只给了方向没有给精确公式的地方，明确标记为：
  - **Book-faithful rule（贴书规则）**
  - **Productization supplement（产品化补充）**

---

## 2. 全书总结构与产品主张

全书可以被压缩为四个产品层：

1. **Avoid Big Risks** → 先排除会永久损失本金的公司
2. **Buy High Quality at a Fair Price** → 只研究高质量公司，并且价格要合理
3. **Don’t Be Lazy—Be Very Lazy** → 极低换手、极少决策、长期持有
4. **Simple Repeatable Process** → 用简单、重复、纪律化流程取胜

因此，产品主流程应改成：

```text
Universe
  -> Hard Reject Filters
  -> Quality Ranking
  -> Fair Price Gate
  -> Concentrated Portfolio / Watchlist
  -> Low-turnover Hold Monitor
```

而不是：

```text
Universe
  -> 30 factors weighted sum
  -> sorted list
```

---

## 3. Introduction → 产品总定位

### 3.1 原书核心思想

导言部分并不在讲某个单独指标，而是在讲：

- 投资不该主要靠预测
- 应该用“进化”的视角理解企业
- 重点是**过程**，不是短期结果
- 本书更像是对 Nalanda 投资方法的“描述”，而不是花哨技巧合集

### 3.2 映射到产品的规则

#### Book-faithful rule
- 产品不能把自己定位成“预测股价涨跌系统”
- 产品应该定位为：
  - **筛选长期优质企业**
  - **避免大错**
  - **在合理价格买入**

#### Productization supplement
- 首页文案、对外口径、详情页解释都应避免使用：
  - 明天涨跌
  - 短线买卖点
  - AI预测股价
- 应改用：
  - 质量等级
  - 估值闸门
  - 长期持有资格
  - 需要继续观察的风险

---

## 4. Chapter 1 — Oh, to Be a Bumblebee

### 4.1 章节主旨

这一章对应 **Avoid Big Risks**。

核心思想不是“如何找到最牛公司”，而是：

- 投资里最重要的是避免大错
- Type I / Type II error 中，更该优先降低会造成本金永久损失的错误
- 治理问题、管理层问题、低质量“turnaround” 公司要高度警惕
- 不要相信自己能靠能力持续修复坏企业

### 4.2 能直接落地的规则

#### Book-faithful rule A：治理问题优先一票否决
如果出现以下信号，应直接排除：

- 财务造假 / 会计丑闻
- 创始人或控制人诚信争议严重
- 监管重大处罚
- 频繁重大关联交易且无法解释
- 审计意见异常

#### Book-faithful rule B：turnaround 不纳入核心股票池
- 书中明显偏向避开“靠翻身叙事驱动”的公司
- 这类公司不应进入主买入池

#### Productization supplement
因为“turnaround”难以完全靠财报字段识别，产品可增加标签：

- `is_turnaround_story`
- `governance_red_flag`
- `accounting_red_flag`
- `regulatory_red_flag`

任一为真，则进入 Reject / Manual Review。

### 4.3 对算法的影响

#### 替换建议
原模型里“治理/风险事件”只是某个因子加减分，权重有限；
应改成：

- **先过滤，再评分**

即：

```text
if governance_red_flag == True:
    reject
```

而不是：

```text
total_score -= 5
```

### 4.4 数据来源建议

#### 美股
- SEC EDGAR：8-K, 10-K, 10-Q, DEF 14A
- 审计意见与重大诉讼：10-K footnotes / risk factors
- 新闻辅助：Reuters / AP / company filings

#### A股
- 交易所公告（上交所 / 深交所）
- 巨潮资讯
- 年报审计意见
- 证监会 / 交易所监管处罚公告

---

## 5. Chapter 2 — The Siberian Solution

### 5.1 章节主旨

这一章对应“如何先把低质量公司筛掉”。

书里最重要、最能直接产品化的一条，是：

> **长期 ROCE 低于 20% 的公司，不值得进入候选池。**

而且作者明确表示，这一步是第一层筛选，不是最后排序。

### 5.2 书中最关键的硬规则

#### Book-faithful rule
- **长期历史 ROCE < 20% → 直接排除**
- 观察窗口：**5–10 年或更长**

这是现有模型必须替换的核心。

### 5.3 为什么 ROCE 如此重要

书中的逻辑链条是：

- 高 ROCE 说明企业有真实竞争力
- 长期高 ROCE 通常意味着企业有定价权、品牌力、效率优势或护城河
- 低 ROCE 公司即便短期便宜，长期通常也不是优质复利机器

### 5.4 对产品的直接改造

#### 现有模型问题
你现在把资本回报相关内容放在“复制力”里，只是若干因子之一。

#### 替换建议
把 ROCE 从普通因子升级为：

- **Universe Filter 的核心入口条件**

```text
if avg_roce_5y < 0.20 and avg_roce_10y < 0.20:
    reject
```

### 5.5 数据来源建议

#### 美股
- SEC XBRL 取 EBIT / operating income、working capital、net fixed assets
- 必要时人工映射 invested capital

#### A股
- 利润表：营业利润 / EBIT
- 资产负债表：应收、存货、应付、固定资产、在建工程、无形资产等

### 5.6 产品化补充

书中没有给出统一的 ROCE 打分曲线，但产品可采用：

- `<20%`：Reject
- `20%–25%`：Pass
- `25%–35%`：Strong
- `>35%`：Exceptional

这属于**产品化补充**，不是书中原句。

---

## 6. Chapter 3 — The Paradox of McKinsey and Sea Urchins

### 6.1 章节主旨

这一章把“高质量公司”进一步拆解成：

- 高资本回报
- 增长
- 低杠杆
- 现金创造能力

作者强调：

- 如果企业增长率低于 ROCE，会持续产生自由现金流
- 债务会显著放大脆弱性
- 最终保护投资者免受鲁棒性丧失的关键，是**买入价格与安全边际**

### 6.2 可直接映射的规则

#### Book-faithful rule A：谨慎负债
- 高质量公司优先选择低杠杆 / 无杠杆
- 不应依赖重债扩张

#### Book-faithful rule B：关注“增长相对于资本回报”的关系
- 增长不是越高越好
- 能在高 ROCE 下增长，且不吞噬现金流，才是好增长

#### Book-faithful rule C：自由现金流能力重要
- 真正好的公司会在增长同时留下现金

### 6.3 产品规则设计

#### Hard Reject / Soft Reject
- Net Debt / EBIT 过高：Reject 或 Manual Review
- Interest Coverage 过低：Reject
- 连续多年 CFO 明显低于净利润：降级

#### Quality Engine
- 质量应同时看：
  - ROCE
  - Revenue CAGR
  - FCF conversion
  - leverage restraint

### 6.4 你现有模型的替换建议

保留以下方向，但调整地位：

- 杠杆
- FCF
- 盈利质量

从“生存力普通加分项”改成：

- **质量引擎核心组成部分**
- 并在极端值时直接触发排除

### 6.5 数据源建议

#### 美股
- SEC XBRL: operatingIncomeLoss, interestExpenseAndOther, cash flow from operations, capex, debt fields

#### A股
- 三大报表即可完成初版
- 若做生产，应使用交易所披露或商业数据库清洗后的标准字段

---

## 7. Chapter 4 — The Perils of a Pavlovian

### 7.1 章节主旨

这一章在讲：

- 市场会被短期新闻、宏观恐慌、情绪波动带偏
- 真正有价值的是：当高质量公司因为短期噪音被错杀时敢于买入
- 2008 年买入 Page 的例子很重要

书中明确给出：

- **买入 Page 时的 trailing TTM PE 为 18x**

### 7.2 关键还原点

#### Book-faithful rule
- 作者不是“任何高质量公司都无脑买”
- 也不是“只买超便宜资产”
- 而是在**高质量 + 市场错杀 + 合理估值**三者同时成立时出手

### 7.3 对舆情/新闻模块的启发

这个章节恰好说明：

- 不能把短期新闻直接映射成评分大幅变动
- 很多新闻噪音反而构成机会

#### 因此产品规则应为：

##### Book-faithful rule
- 新闻不能直接重写企业长期质量分

##### Productization supplement
- 新闻事件进入 `Event Risk Layer`
- 只产生：
  - 信息标签
  - 观察状态
  - 人工复核提示
- 不应在默认模式下直接把总分砍掉很多分

### 7.4 你问的“重大舆情是否马上改评分”

按本书思想，更合理的做法是：

- **不直接改长期质量分**
- 先改：
  - `watch_status`
  - `headline_risk`
  - `manual_review_required`

只有当新闻对应到：

- 治理问题
- 财务造假
- 资本配置失真
- 结构性竞争力恶化

才通过人工或高置信度规则改变质量判断。

---

## 8. Chapter 5 — Darwin Ate My DCF

### 8.1 章节主旨

这是全书中对“如何估值”最重要的一章之一。

核心思想：

- 不迷信复杂 DCF
- 不依赖精细远期预测
- 以历史表现和可验证经营轨迹为核心
- 更关注“这是不是一个经过验证的高质量公司”

书里强调：

- 未来预测兴趣不大
- 研究历史比构建未来故事更可靠

### 8.2 对产品的核心影响

#### Book-faithful rule A
- 不要把产品做成“预测未来十年现金流”的机器

#### Book-faithful rule B
- 详情页、算法解释页应以**历史验证**为主

### 8.3 替换建议

原模型若大量依赖：

- forward PE
n- analyst estimates
- future earnings forecast

则与本书精神不一致。

更贴书的做法应是：

- 优先 trailing metrics
- 优先历史 ROCE / growth / margins / cash conversion
- DCF 仅作为附属参考，不作为核心排序依据

### 8.4 产品化实现

详情页重点展示：

- 5y / 10y ROCE
- 5y / 10y revenue CAGR
- 5y / 10y margin history
- 5y / 10y FCF conversion
- 估值历史分位

而不是默认先展示：

- 分析师目标价
- forward EPS narrative

---

## 9. Chapter 6 — Bacteria and Business Replay the Tape

### 9.1 章节主旨

这一章在讲**模式复现 / convergent patterns**：

- 优秀企业并非完全随机出现
- 某些行业、某些商业模式会反复出现相似的高质量特征
- 投资者应建立“模式识别能力”

### 9.2 产品含义

#### Book-faithful rule
- 产品不只做单公司打分，还应支持**同类优质模式识别**

### 9.3 功能建议

#### Productization supplement
新增：

- `Pattern Library`
- `Comparable Great Businesses`
- `Business Model Archetype`

例如：

- 轻资产消费品牌型
- 渠道与分销强化型
- 品牌+定价权型
- 资产周转优异型

### 9.4 对算法的作用

不是直接加入一个新财务因子，而是形成：

- **解释层**
- **行业内高质量公司对照层**

即：

> 这家公司为什么像历史上那些高质量复利企业？

---

## 10. Chapter 7 — Don’t Confuse a Green Frog for a Guppy

### 10.1 章节主旨

这一章在讲“信号与噪音”。

核心意思：

- 很多投资者关注了大量无用信息
- 工厂参观、花哨发布会、PR、表面热度，不一定是有用信号
- 应该把精力集中在真正决定企业长期竞争力的东西上

### 10.2 对产品的直接影响

#### Book-faithful rule
- 弱信号不能高权重进入模型

### 10.3 不该高权重使用的数据

- 普通新闻热度
- PR 稿数量
- 社交媒体表层讨论热度
- 管理层“好听的话”本身

### 10.4 可以作为低权重提示层的数据

- 高频新闻
- 搜索热度
- 社媒情绪

但只能放在：

- `Signal Layer: Low-confidence`
- `Manual Review`

不能替代核心财务和商业质量判断。

### 10.5 你关于“每天爬新闻并重大舆情马上改分”的答案

按本章逻辑：

- **可以爬新闻**
- **不应该默认直接改长期评分**

更合理的是：

```text
News ingestion
  -> event classification
  -> confidence scoring
  -> risk label / watchlist flag
  -> optional manual override
```

---

## 11. Chapter 8 — Birds and Bears Bare an Aberration

### 11.1 章节主旨

这一章强调：

- 世界并不平滑
- 企业经营、股价表现都可能出现“异常年份”
- 好公司也会有难看的短期波动

### 11.2 产品规则

#### Book-faithful rule
- 不要因为单一年份异常就机械否决公司

### 11.3 替换建议

质量评估不能只看单年数据，应采用：

- 多年平均
- 中位数
- 滚动窗口
- 趋势判断

### 11.4 产品化实现

对于以下指标，优先使用 5y / 10y 处理：

- ROCE
- Revenue growth
- EBIT margin
- FCF conversion
- leverage

而不是单年值。

### 11.5 这对你的现有模型意味着什么

如果你有很多“年度点状因子”，应整体改成：

- rolling average
- rolling median
- worst-year + average combination

这更符合原书思想。

---

## 12. Chapter 9 — Eldredge and Gould Dredge Up Investing Gold

### 12.1 章节主旨

这一章是“低换手 / 长期持有 / 少做决策”的理论高地。

核心意思：

- 极少数伟大投资决定，决定大部分长期收益
- 不需要一年做很多次聪明决策
- 好公司很多时候不是买不到，而是拿不住

### 12.2 产品规则

#### Book-faithful rule A
- 产品不能鼓励频繁调仓

#### Book-faithful rule B
- 回测系统应验证：
  - 低换手版本
  - 长持版本

### 12.3 回测 PRD 应如何调整

应新增比较：

- 月调仓
- 季调仓
- 年调仓
- 长持不动

看哪种更符合本书精神及实际表现。

### 12.4 持仓监控规则

产品应优先触发“卖出/降级”的原因包括：

- 治理恶化
- 商业模式破坏
- 资本回报持续下滑
- 估值极端脱离长期合理区间

而不是：

- 短期波动
- 一条新闻
- 单季 miss

---

## 13. Chapter 10 — Where Are the Rabbits?

### 13.1 章节主旨

这一章是在讲：

- 长期财富创造高度集中在少数 exceptional businesses
- 与其广撒网买 mediocre businesses 的低估值，不如耐心等待极少数 exceptional businesses 的合理价格

### 13.2 核心产品含义

#### Book-faithful rule A
- 不投资 mediocre / low-quality businesses，哪怕它们看起来便宜

#### Book-faithful rule B
- 股票池应该是“少而精”的

### 13.3 对当前产品排序逻辑的替换建议

不要输出一个看似完整的全市场分数排名，鼓励用户在低质量股票里也做比较。

更贴书的做法是：

- 先大规模过滤
- 剩下少量真正合格公司
- 再看是否到了合理价格

### 13.4 UI 建议

不要只给一个 `rank #153 / 5000`。

更贴书的是：

- `Rejected`
- `Qualified but too expensive`
- `Qualified and near fair price`
- `High conviction candidate`

---

## 14. Conclusion — Honeybees Win by Repeating a Simple Process

### 14.1 结论主旨

结论部分把方法压缩成一套纪律：

- 只投 exceptional businesses
- 在 attractive valuation 买入
- 很少交易
- 简单而可重复

### 14.2 原书思想可压缩成的产品总原则

#### Book-faithful rule 1
- 先过滤，后排序

#### Book-faithful rule 2
- 质量比估值更重要，但价格仍然重要

#### Book-faithful rule 3
- 估值是闸门，不是替代质量的理由

#### Book-faithful rule 4
- 少做动作，少做预测，少做过度复杂建模

### 14.3 最终系统形态

```text
Step 1. Reject fragile / poor-quality companies
Step 2. Identify exceptional businesses using long history
Step 3. Wait for fair price
Step 4. Buy meaningfully
Step 5. Hold for long periods unless thesis breaks
```

---

## 15. 全书映射后的新系统结构

## 15.1 原系统

```text
30 因子 -> 加权总分 -> 排序
```

## 15.2 新系统

```text
A. Hard Reject Filters
   - governance
   - accounting
   - leverage extremes
   - long-term ROCE below threshold

B. Quality Engine
   - long-term ROCE
   - growth with cash generation
   - margin resilience
   - balance sheet conservatism
   - business model repeatability

C. Fair Price Gate
   - trailing valuation vs own history
   - valuation vs market context
   - margin of safety

D. Hold / Monitor
   - thesis intact?
   - governance deterioration?
   - quality break?
   - valuation extreme?

E. Event Risk Layer
   - labels only by default
   - no automatic heavy score override
```

---

## 16. 书中明确数字与产品使用方式

以下是目前从原书中已经确认、可以进入 PRD 的关键数字：

### 16.1 明确数字

- **长期历史 ROCE < 20%：排除**
- **Nalanda 组合买入时的 median trailing PE = 14.9x**
- **印度主要市场长期 median PE 约 19.7x**
- **Page 买入时 trailing TTM PE = 18x**
- 作者表述：**很少支付超过 20x trailing PE**

### 16.2 使用原则

这些数字应这样使用：

#### 可以直接使用
- `ROCE 20%` 作为硬门槛

#### 可以作为估值风格锚点
- `14.9x` / `18x` / `rarely > 20x` 可作为**估值风格基准**

#### 不能被误写成普适铁律
- 不能简单写成：
  - “PE > 20 一律不投”

更准确的表达应是：

> 本书作者的历史买入风格显示，他通常在 trailing PE 约 15x 左右买入，18x 也会买，且极少支付高于 20x 的 trailing PE；但书中并未把某个统一 PE 数字定义为所有行业、所有公司的一刀切绝对红线。

---

## 17. 对你下一版产品的直接建议

### 17.1 立刻要改的

1. 把 **ROCE < 20% 排除** 提到最前面
2. 把估值从“总分项”改成“买入闸门”
3. 把新闻舆情从“实时改总分”改成“事件风险标签层”
4. 把单年因子改成多年滚动指标
5. 把“全市场精细排序”改成“合格 / 不合格 / 值得等 / 可买”

### 17.2 下一步该补的

1. 模式识别解释层（Chapter 6）
2. 低换手回测（Chapter 9）
3. 持仓监控而非频繁调仓（Chapter 9–10）

---

## 18. 本部分结论

这本书对应的产品，并不是一个：

- 高频打分器
- 新闻驱动器
- 预测型估值器
- 全市场综合排名器

它更像一个：

- **高质量企业筛选系统**
- **合理价格等待系统**
- **低换手长期持有系统**
- **用纪律避免大错的系统**

如果你要“替换现有模型”，真正该替换的不是几个因子权重，而是**系统哲学**：

> 从“用很多因子算一个分数”
> 变成
> “先排除，再确认质量，再等价格，再长期持有”。

---
