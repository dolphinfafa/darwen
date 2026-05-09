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

