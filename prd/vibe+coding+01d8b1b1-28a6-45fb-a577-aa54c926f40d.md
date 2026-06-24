### 财务风险过滤

下面给出一套**严格贴合原书“低负债、现金流稳健、不要碰脆弱公司”逻辑**的财务风险层。所有阈值均为**工程建议**，原书未给出精确公式或边界时，下面均已显式视为 implementation recommendations。

|指标|公式|默认阈值 / 分档|默认动作|数据源|实现备注|
|-|-|-|-|-|-|
|净负债/EBIT|`NetDebt = STDebt + LTDebt + LeaseLiab - Cash - STInvestments`; `ND_EBIT = NetDebt / EBIT`|`<=1` 通过；`1~2.5` 软警告；`>3` 自动剔除|Hard / Soft|SEC companyfacts；Tushare 三表；Polygon 可作缓存|取最新完整 FY；并看近 3Y 中位数；若 `EBIT<=0 且 NetDebt>0` 直接剔除|
|利息保障倍数|`IC = EBIT / abs(InterestExpense)`|`>=5` 通过；`3~5` 软警告；`<3` 自动剔除|Hard / Soft|SEC/Tushare|若净现金且利息费用极低，可豁免|
|负 FCF 年数|`FCF = CFO - CapEx`; 统计近 5Y `FCF<0` 年数|`0~1` 通过；`2` 软警告；`>=3` 自动剔除|Hard / Soft|SEC/Tushare 现金流量表|CapEx 默认取购建固定资产/无形资产/长期资产现金支出；若缺失，记 `metric_missing`|
|FCF 波动|`FCF_margin = FCF / Revenue`; `CV_5Y = std(FCF_margin)/abs(mean(FCF_margin))`|`<=0.5` 通过；`0.5~1` 软警告；`>1` 对非周期股自动剔除|Hard / Soft|SEC/Tushare|周期行业只做 soft；建议与行业标签联动|
|经营现金与利润匹配|`CFO_NI = sum(CFO_5Y) / sum(NI_5Y)`|`>=0.9` 通过；`0.6~0.9` 软警告；`<0.6` 自动剔除|Hard / Soft|SEC/Tushare|反映利润兑现能力；对重资产扩张期公司可加人工复核|
|应计利润率|`Accruals = (NI - CFO) / AvgTotalAssets`，取近 3Y 平均|`<=5%` 通过；`5%~10%` 软警告；`>10%` 自动剔除|Hard / Soft|SEC/Tushare|高正应计通常意味着利润质量偏弱；与 Beneish 联动更稳|
|Altman Z / Z''|制造业用 `Z = 1.2WC/TA + 1.4RE/TA + 3.3EBIT/TA + 0.6MVE/TL + 1.0Sales/TA`；非制造业用 `Z'' = 6.56WC/TA + 3.26RE/TA + 6.72EBIT/TA + 1.05BVE/TL`|`Z<1.8` 或 `Z''<1.1` 自动剔除；灰区软警告|Hard / Soft|SEC/Tushare + 行情市值|金融/保险已在 Q0 排除；行业版本不能混用|
|应收增长领先收入|`ARGap = CAGR(AR,3Y) - CAGR(Revenue,3Y)`|`<=5pct` 通过；`5~15pct` 软警告；`>15pct` 自动剔除|Hard / Soft|SEC/Tushare|尤其适合识别渠道压货与回款恶化|
|存货增长领先收入|`InvGap = CAGR(Inventory,3Y) - CAGR(Revenue,3Y)`|`<=5pct` 通过；`5~15pct` 软警告；`>15pct` 对库存行业自动剔除|Hard / Soft|SEC/Tushare|对软件/轻资产行业不适用，自动标记 N/A|
|CCC 恶化|`CCC = DSO + DIO - DPO`; `ΔCCC = median(last2Y) - median(first2Y)`|`<=10天` 通过；`10~30天` 软警告；`>30天` 且 `CFO/NI<0.8` 自动剔除|Soft / Hard|SEC/Tushare|绝对 CCC 不跨行业比，主要看趋势与 peer z-score|
|Beneish M-score|标准 8 因子模型|`<=-1.78` 通过；`>-1.78` 软警告；如叠加重述/处罚则自动剔除|Soft → Hard|SEC/Tushare + 公告|单独使用误伤较高，建议只做会计风险联动指标|

这套财务风险层的精神与原书是一致的：**高 ROCE 只是入场券；真正要避免的是“高 ROCE + 高负债 + 现金流差 + 利润质量弱”这种伪优质公司。建议把其中最强的四个指标——`净负债/EBIT`、`利息保障倍数`、`负 FCF 年数`、`CFO/NI`——定义为财务硬闸门**；其余指标先作为**软过滤或联动硬过滤**。这样既能保持纳兰陀式的克制，又能减少 false positive。

### 商业风险过滤

商业风险层要尽可能把原书中的“客户多元、供应商多元、竞争壁垒、行业变化慢”变成可执行指标。这里最重要的区别是：**客户/供应商集中度最接近原书硬逻辑，应该优先做 hard/soft 混合；而市场份额、产品重复性、单位经济学等，更适合先做 soft layer。**

|指标|公式 / 定义|默认阈值 / 分档|默认动作|数据源|实现备注|
|-|-|-|-|-|-|
|客户集中度|`Top1CustomerShare`，`Top5CustomerShare`|`Top1<=20%` 且 `Top5<=50%` 通过；`Top1 20~30%` 或 `Top5 50~70%` 软警告；`Top1>30%` 或 `Top5>70%` 自动剔除|Hard / Soft|年报附注、10-K、20-F、A股年报；付费可用 FactSet/Bloomberg/Panjiva|美股大客户>10%收入通常披露；A股年报一般可抽出前五大客户占比|
|供应商集中度|`Top1SupplierShare`，`Top5SupplierShare`|`Top1<=20%` 且 `Top5<=50%` 通过；`Top1 20~30%` 或 `Top5 50~70%` 软警告；`Top1>30%` 或 `Top5>70%` 自动剔除|Hard / Soft|年报、采购附注、A股年报；付费可用 FactSet Supply Chain / Panjiva / ImportGenius|供应商披露完整度弱于客户；缺失时默认 soft、不做 hard|
|收入增长稳定性|`RevVol = std(YoYRevenueGrowth,last5Y)`；另统计 `DeclineYears_5Y`|`RevVol<=10pct` 且 `DeclineYears<=1` 通过；中间区间软警告；`RevVol>20pct` 且 `DeclineYears>=3` 自动剔除（非周期行业）|Hard / Soft|SEC/Tushare|周期行业只做 soft，并转交行业风险层处理|
|毛利率稳定性|`GM = GrossProfit/Revenue`; `std(GM,last5Y)`|`<=3pct` 通过；`3~6pct` 软警告；`>6pct` 对消费/软件/平台型企业自动剔除|Hard / Soft|SEC/Tushare|先按行业分组做 z-score，再看绝对值|
|相对行业增长差|`GrowthGap = median(CompanyRevYoY - PeerMedianRevYoY,last3Y)`|`>=0` 通过；`-5pct~0` 软警告；`<-5pct` 软警告或自动剔除（若公司自称龙头）|Soft / Conditional Hard|Tushare/Polygon + 行业分类 + 付费行业数据|需要 peer group；若行业统计缺失则回退到同一级行业中位数|
|产品/业务集中度|`HHI = Σ(segment_share_i^2)`|`<0.5` 通过；`0.5~0.75` 软警告；`>0.75` 软警告，单一产品且产品周期短则自动剔除|Soft / Conditional Hard|Segment disclosure、A股主营构成|单一产品不必天然否定，但若叠加快变行业则显著加风险|
|重复性收入 / 可重复性|`RecurringShare = RecurringRevenue / Revenue`；若无则用 `ContractLiabilities/Revenue` 或递延收入 proxy|行业通用硬阈值 **unspecified**；建议用 peer percentile：后 40% 软警告|Soft|年报/10-K 文本抽取、AlphaSense/Quartr 可增强|原书强调“商业模式可重复”，但通用统一阈值不存在|
|单位经济学 proxy|通用代理建议：`GrossProfit / AvgInvestedCapital`、`Sales / AvgInventory`、`Sales / AvgNetFixedAssets`；行业专属 KPI 优先|通用硬阈值 **unspecified**；建议与自身 5Y 历史和 peer rank 对比|Soft|SEC/Tushare + 文本披露 + 行业付费数据|统一硬阈值不可取；更适合行业插件化|
|市场份额 proxy|`RevenueGrowth - IndustryGrowth`，或数字业务用 `traffic / MAU / 下载量` 代理|`连续 3Y 为负` 软警告；`连续 5Y 为负` 且毛利率同步下滑 → 自动剔除|Soft / Conditional Hard|行业报告、Similarweb、data.ai、Wind/FactSet|市占率本身常需付费，先做 proxy，不强行统一|
|订单/复购稳定性|若披露订单储备、会员续费率、同店销售、续签率，则直接抽取；否则 N/A|阈值依行业插件定义；默认 soft|Soft|年报、电话会、投资者日材料|由 AI 抽结构化字段，必须存证据片段|

商业风险层最关键的工程点，不是阈值，而是**数据取得顺序**。建议按“**结构化披露 → 正则抽取 → LLM 证据抽取 → 付费补数**”四级回退。A 股年报里通常能抽到前五大客户/供应商占比，美股则对大客户收入集中通常有披露，但供应商集中信息经常不完整，所以供应链关系数据极度适合引入 FactSet、Bloomberg SPLC、Panjiva、ImportGenius 这类数据源。对缺失严重的字段，默认应该是“**缺失不自动剔除，但降低业务风险层的自动化级别，转人工复核**”。这个策略比盲目填补或强推 AI 推断更稳健。巨潮资讯作为法定披露平台、并提供公告、问询函、股东数据、高管持股与数据 API 入口，非常适合做 A 股商业与治理文本的真值层。

## 治理与行业风险设计

治理风险和行业风险最容易“AI 讲得头头是道、但证据不足”。因此这里的设计原则必须是：**能用官方硬事实就不用情绪；能用公告原文就不用二手新闻；AI 只能做抽取和归纳，不能跳过证据链。**

### 治理风险指标

|指标|规则|默认动作|数据源|备注|
|-|-|-|-|-|
|审计意见异常|保留意见/否定意见/无法表示意见|自动剔除|年报审计报告、10-K/20-F、A 股年报|典型 hard fact|
|审计师更换|3Y 内 1 次软警告；5Y 内 `>=2` 次自动剔除|Soft / Hard|美股 8-K Item 4.01；A 股公告/年报|8-K 明确有 auditor change 事项，且 8-K 一般四个工作日内报送|
|财务报表不再可靠 / 重述|出现 8-K Item 4.02、重大会计差错更正|自动剔除|SEC 8-K、A 股公告|硬治理红旗|
|正式立案/重大处罚|最近 36 个月有 SEC/CSRC 立案、行政处罚、交易所纪律处分|自动剔除|SEC、巨潮、交易所监管页面|优先官方源|
|关联交易强度|`RPTAmount / Revenue` 或 `/TotalAssets`；`>5%` 自动剔除，`2~5%` 软警告|Hard / Soft|Proxy/年报附注、A 股年报|需识别“经常性合理交易”与异常输送|
|控制权与经济利益背离|`VotingRights / EconomicRights > 2` 软警告；`>5` 自动剔除|Soft / Hard|Proxy、章程、招股书、DEF14A|双重股权结构企业适用|
|大股东质押率|A 股控股股东股份质押比例 `>30%` 软警告；`>50%` 自动剔除|Soft / Hard|巨潮股东数据/股权质押、Wind/Choice|A 股非常实用|
|独立董事/董事会独立性|低于法规或交易所最低要求自动剔除；低于最佳实践软警告|Hard / Soft|Proxy、年报、治理章节|阈值受市场规则约束，需配置化|
|内部人净卖出|`NetInsiderSell / MarketCap`，90D `>0.3%` 软警告；`>1%` 且无买入、且 CFO/CEO 主导时升级|Soft|SEC Form 4/3/5；巨潮高管持股/增减持|US 的 Form 4 需在交易后第二个工作日前提交，适合做近实时治理信号|
|股本稀释|`ShareCount CAGR_3Y > 5%` 软警告；`>10%` 且 FCF/share 不增自动剔除|Soft / Hard|SEC/Tushare + 股本字段|“对少数股东不友好”的工程代理|

治理层的自动化建议是：**只有“审计意见异常、重述、不再可靠、正式立案处罚、法规不合规”这类硬事实，才做 hard filter；内部人减持、控制权结构、关联交易、稀释等，先默认 soft，再叠加证据升级。**SEC 的 8-K 表单明确包含 `Item 4.01 Changes in Registrant’s Certifying Accountant` 与 `Item 4.02 Non-Reliance on Previously Issued Financial Statements`，且 Form 4 明确要求在变动后第二个工作日前提交，这使得美股治理监控非常适合做事件驱动更新。

### 行业风险指标

|指标|规则|默认动作|数据源|备注|
|-|-|-|-|-|
|行业变化速度|维护 `industry_change_tier = slow / medium / fast` 行业字典；`fast` 默认软警告|Soft|手工行业映射 + 历史波动统计 + AI 文本审阅|这是最贴近原书“行业变化慢”的做法|
|周期性暴露|`std(EBITMargin,10Y)`、`RevenueDownYears_10Y`、与 PMI/商品价格相关性|默认 soft；若 `cyclical=true` 且 `NetDebt/EBIT>2` 自动剔除|Soft / Hard|财务历史 + 宏观序列|
|技术替代压力|`3Y` 相对行业增长持续落后 + 毛利率下滑 + 文本出现替代技术/平台迁移/份额流失|Soft；证据强时自动剔除|Soft / Conditional Hard|年报风险因素、电话会、新闻、行业报告|
|监管强度|24M 内监管函/问询函/处罚数量|`>=1` 正式调查自动剔除；多次问询软警告|Hard / Soft|巨潮、交易所、SEC、8-K|
|资产减值 / 技术陈旧|`Impairment / AvgAssets` 3Y 连续偏高|`>2%` 软警告；`>5%` 自动剔除|Soft / Hard|年报附注|
|行业法规依赖|收入对牌照/补贴/单一政策的依赖高|默认 soft；政策变更后升级|Soft|年报文本、监管公告、行业数据库|

行业风险层最值得强调的是：**不要把“快变化行业”做成一刀切的自动淘汰**。原书确实偏好变化慢的行业，但工程上更稳妥的做法是：**行业快变化 = 基础软警告；快变化 + 杠杆高 + 收入不稳 + 毛利率塌陷 = 自动剔除。**这能避免错杀一切技术行业，也更接近“避免第一类错误”的精神。

## 数据源与信号体系

### 结构化财务与披露数据

建议把数据源分成“真值源、工作流源、增强源”。真值源负责回测与最终判定；工作流源负责工程效率；增强源负责补齐商业/治理/行业信息。

|数据源|主要用途|覆盖/优势|更新/延迟|成本|API 易用性|建议角色|
|-|-|-|-|-|-|-|
|SEC EDGAR `data.sec.gov`|美股 filings、companyfacts、submissions|官方、XBRL 标准化、无需 key|filings 实时、XBRL 通常分钟级、bulk nightly|免费|中|**美股真值源**|
|Polygon / Massive|美股行情、新闻、新闻情绪|行情/新闻一体、ticker 映射好|新闻 hourly；免费 2 年历史，付费全历史|Free / $29 / $79 / $199 月费|高|**美股工作流源**|
|Tushare|A 股三表、行情、日指标、研发效率高|Python/REST 接入方便|依接口与权限而定|官方公开价格 **unspecified**|高|**A 股工作流源**|
|巨潮资讯|A 股法定公告、问询函、监管措施、股东数据、数据 API|官方披露平台，覆盖深沪京与大量治理信息|公告级实时/准实时|基础免费，数据服务/API **quote-based / unspecified**|中|**A 股真值源**|
|GDELT|全球新闻弱信号、多语言翻译、主题/情绪|65 语言、15 分钟更新、免费|15 分钟|免费|中|**新闻增强源**|
|NewsAPI|广谱媒体搜索与历史文章|商业媒体覆盖广|开发免费但有 24h 延迟；生产业务付费实时|$0 / $449 / $1749 月费|高|**备选新闻源**|
|Wind / iFinD / Choice|A 股企业级终端/API/行业数据|深度研究、行业与股东/事件完备|高|报价制，公开价格 **unspecified**|中|**A 股增强源**|
|FactSet / LSEG / CapIQ|供需链、细分行业、segments、文本增强|商业关系与行业数据更强|高|报价制，公开价格 **unspecified**|中|**商业风险增强源**|
|AlphaSense / RavenPack|文本与事件语义|文本搜索/语义标签强|高|报价制，公开价格 **unspecified**|中|**治理/行业 AI 增强源**|

SEC 官方说明其 API 无需认证、提供 company facts 与 submissions，并在披露时实时更新，且 nightly 发布 bulk ZIP，非常适合作为美股点时仓的底座。Polygon 的新闻接口公开写明可按 ticker 与 `published_utc` 检索，且在响应中直接给出 `publisher`、`keywords`、`tickers`、`published_utc` 与 `insights` 字段；同一页也明确给出了股票套餐的公开价格与 News 历史深度。Tushare 官方首页说明其支持 Python 与 Restful HTTP，且面向量化与 AI 场景；巨潮则明确自己是法定披露平台，并在首页公开列出公告、问询函、监管措施、股东数据、高管持股和数据 API 入口。GDELT 则适合作为全球低成本弱信号层。

### 推荐的新闻与社交信号层

你的系统最稳妥的信号优先级建议如下：

**第一级：官方披露**
美股：10-K、10-Q、8-K、Proxy、Forms 3/4/5。
A 股：巨潮公告、交易所问询函/监管措施/纪律处分、股东增减持、高管持股。
这一级是**唯一可以触发 governance/controversial hard filter 的文本源**。

**第二级：结构化新闻**
首选 Polygon News；备选 NewsAPI；全球弱信号用 GDELT。Polygon News 能直接返回情绪 insights、关键词、tickers 与发布时间；NewsAPI 的开发版明确只允许开发测试、且有 24 小时延迟，生产必须切付费商务计划；GDELT 适合做跨语言召回与异常词频监控。

**第三级：高价值付费语义源**
如果预算允许，优先考虑：
美股文本：AlphaSense、RavenPack、FactSet/LSEG 文本。
A 股文本：Wind/Choice/iFinD、巨潮数据服务。
这一级的价值不在于“更快”，而在于**更稳的实体标准化与更干净的企业事件标签**。

