# Darwen 开发文档（接手指南）

> 最后更新：2026-06-19 ｜ 版本 V2.1（三层漏斗：ROCE → 稳健性 → 风险性）
> 权威需求见 prd/v2.0/Darwen_V2_PRD_Master.md；逐日变更见 milestones/*.md。

## 0. 定位
基于 Pulak Prasad《What I Learned About Investing from Darwin》方法论的股票筛选系统：
先用长期 ROCE 筛优质公司，再过滤稳健性/风险性，输出值得研究的候选。不做评分总分、不做买卖信号。

## 1. 快速开始
- Python 3.10（conda env darwen），解释器 /opt/miniconda3/envs/darwen/bin/python
- MySQL 8 本地 127.0.0.1:3306/darwen（配置 .env，严禁连生产）
- 后端 FastAPI+SQLAlchemy+Alembic 端口 15003；前端 Vue3+Vite 端口 15002（自研UI无组件库）
- 启动后端：/opt/miniconda3/envs/darwen/bin/uvicorn backend.main:app --host 127.0.0.1 --port 15003
  （开发建议加 --reload --reload-dir backend）
- 启动前端：cd frontend && npm run build（产物 dist/，nginx/dev_web 反代 base=/darwen/）
- API 前缀 /darwen/v1 /darwen/v2 → 127.0.0.1:15003；默认管理员 admin
- 头号坑：线上进程无 --reload，改后端代码必须重启进程才生效（否则新端点404/跑旧引擎）

## 2. 目录结构
backend/
- main.py 入口+路由注册+建表/admin；config.py/database.py
- models/ ORM表；schemas/v2.py Pydantic模型
- api/ auth admin user_settings screening backtest companies watchlist
- screening/ ★筛选引擎
  - funnel_v2.py ★现行三层漏斗引擎（ROCE→稳健→风险+分层gate）
  - config.py ScreenConfig（阈值/ai_mode/回溯年数+ai_enabled_for）
  - q_layer.py ROCE层（evaluate_roce_gate 按N年现算）；exclusion.py Q0排除
  - reason_codes.py/reason_labels.py 原因码+中文
  - funnel.py/r_layer.py/v_layer.py/status_resolver.py 旧Q/R/V（deprecated保留）
- ai/ ★AI风险层
  - orchestrator.py analyze_layer(layer) 编排：证据→provider→融合→落库
  - prompts/ sturdiness_filter(稳健4类)/risk_filter(风险8类)/version
  - schema.py RiskAIOutput+STURDINESS_LABELS/RISK_LABELS；crypto.py Fernet加密key
  - chatgpt_provider/minimax_provider/provider_base
- metrics/ ★指标预计算→metric_periodic
  - roce.py（ROCE严格口径+compute_roce_series+evaluate_quality_gate）
  - leverage/cash_quality/dilution/valuation
  - compute.py persist_all_metrics_bulk（year_range默认(2014,2025)）；field_map.py
- pipeline/ ★数据接入：sec_edgar(美股SEC) cn_stock_v2(A股Tushare) news(Polygon) market_data(行情)
- tests/test_roce_gate.py（15用例）
frontend/src/ router/index.js api/index.js views/ components/ composables/useReasonLabels.js
其他：migrations/versions milestones prd/v2.0 docs .agent/workflows

## 3. 核心业务：三层漏斗（V2.1）
流程：选股票池(内嵌ROCE阈值+回溯年数+AI介入)→创建run
 →①ROCE门槛(规则)──暂停awaiting_review·人工放行/剔除
 →②稳健性(规则+AI)──暂停·人工
 →③风险性(AI)──暂停·人工
 →定稿finalize→入选(通过三层)
- 入口 POST /v2/screen-run → funnel_v2.start_run（后台跑ROCE层）
- 推进 POST /v2/screen-run/{id}/advance → run_from(next)；risk后 finalize_run
- 人工 POST /v2/screen-run/{id}/manual（force_pass/force_reject）
- 视图 GET /v2/screen-run/{id}/funnel；auto_advance=true 三层连跑

### 3.2 引擎 screening/funnel_v2.py（最重要）
- 存活集不变量：screen_result.rejected_at_layer IS NULL = 存活/入选；某层不通过标 rejected_at_layer=层名
- 计数守恒：total = 存活 + Σ各层出局
- 关键函数：run_from / finalize_run / _run_roce_layer / _run_ai_layer /
  _eval_roce _eval_sturdiness _eval_risk / _run_layer_ai(AI用独立session) / _config_from_run
- screen_run 状态：current_layer(roce/sturdiness/risk/done) layer_status(running/awaiting_review/completed/failed) auto_advance status
- 前端判断完成/失败以 status 为准，不要只看 layer_status（历史bug）

### 3.3 ①ROCE层 q_layer.py
- Q0排除(银行/保险/REIT/ETF/SPAC/ADR…)
- 按N年现算(可配3/5/7/10)：evaluate_roce_gate(rows,threshold,lookback_years)
  short=N(通过=中位数≥threshold且达标≥ceil(0.8N)；近N年缺失≥2→Q5覆核)；long=2N(strong/Q4)
  N=5与旧5Y/10Y口径等价(单测护栏)；读metric_periodic逐年roce按日历年去重
- ROCE公式(metrics/roce.py)：EBIT/(净营运资本〔剔超额现金〕+净PPE)
  负营运资本公司(Apple/Visa)roce=None走Q5（正常非bug）

### 3.4 ②稳健/③风险层+AI双层
- 稳健：无负债有现金流(规则net_debt/EBIT·利息保障·FCF)；多元化客户/供应商·行业变化慢·稳定管理(AI)
- 风险：不诚信/转型/并购/靠预测/不善待相关方(AI 8类标签)
- AI走 ai/orchestrator.analyze_layer(layer)：财务摘要+text_document证据→provider→融合规则
  (REJECT需高置信≥0.8+法定披露佐证；仅新闻最高REVIEW)→落risk_ai_result(含layer)
- prompt分sturdiness_filter/risk_filter；改prompt必须bump prompts/version.py
- funnel中仅overall_action==REJECT才过滤；其余放行交人工

### 3.5 AI介入范围 ai_mode
ScreenConfig.ai_mode + ai_enabled_for(layer)：
off 不调AI(稳健只规则·风险占位放行) | key_stage 仅风险层 | full 稳健+风险层全程
前端选股页"AI介入"下拉传入；未绑key自动降级(标待AI,不报错但不生效)

## 4. 数据库核心表
- company: company_id market(US/CN_A) cik stock_code instrument_type fiscal_year_end_month is_excluded
- security: ticker exchange(1:N)
- fact: concept period_end fiscal_year value accepted_date(防前视) source_type
- metric_periodic: metric_name(roce/net_debt_ebit/…) period_end value formula_version ★
- metric_lineage_log: 血缘
- filing/text_document: source_type(SEC/CNINFO/PG-NEWS…) published_at content_url
- screen_run: status current_layer/layer_status/auto_advance config_snapshot universe_snapshot progress_count
- screen_result: status rejected_at_layer/layer_results/manual_action reason_codes metrics_snapshot ai_result_id
- risk_ai_result: layer(sturdiness/risk) overall_action labels(含evidence_doc_ids) prompt_version
- watchlist/watchlist_item: user_id,name / company_id,source_run_id,note
- user: chatgpt/minimax_api_key_encrypted(Fernet) ai_provider_default
※ Schema变更必须经Alembic迁移(加列只能靠迁移)；严禁手动ALTER

## 5. 数据管道与指标计算
- 美股：财报SEC EDGAR XBRL(pipeline/sec_edgar) 行情yfinance 新闻Polygon
- A股：财报Tushare Pro(pipeline/cn_stock_v2) 行情akshare 无新闻
- 美股重拉财报：python -m backend.pipeline.sec_edgar.backfill_tags（全量548；只INSERT缺失年份,点时安全）
- A股拉财报：python -m backend.pipeline.cn_stock_v2.runner（runner仅10家样本；全量需遍历company表CN_A）
- 重算指标：persist_all_metrics_bulk(company_ids=...)（year_range默认(2014,2025)）
- 新财年流程：先拉财报(backfill/tushare)→再重算指标→重启后端。缺一不可
- metric_periodic.roce上限=compute.py的year_range(当前2025,每年初手动更新)+fact是否拉到该财年

## 6. 后端API(V2,前缀/v2)
companies industries universe/presets｜screen-run(POST启动) screen-run/{id}(状态)
screen-run/{id}/funnel(★漏斗) advance(★推进/定稿) manual(★人工) result/{cid}(详情)
my-runs PATCH my-runs/{id}(改名)｜watchlists CRUD + items + add-company
company/{cid}/evidence?doc_ids= filing-url profile analysis-prompt｜reason-codes/labels｜v1/user/api-key
OpenAPI: http://127.0.0.1:15003/openapi.json

## 7. 前端页面
/universe UniverseConfig(★选股+ROCE/回溯年数/AI介入→启动)
/funnel/:runId FunnelResults(★三层漏斗+人工gate放行/剔除/推进)
/run/:runId/company/:cid CompanyDetailV2(历史ROCE+过滤原因+出处+入池)
/my-runs MyRuns(历史+行内改名)｜/my-watchlists MyWatchlist｜/account AccountSettings(绑key)
/config /results ScreenConfig/ScreenResults(deprecated旧流程无导航)
API封装api/index.js(自动Bearer token,401跳登录)；reason中文useReasonLabels.js；主色#4285f4

## 8. 部署运维
- 后端重启：kill <pid> → nohup uvicorn backend.main:app --host 127.0.0.1 --port 15003 &（改后端代码后必须做）
- 端口：ss -ltnp|grep 15003；全局 curl -s http://localhost:555/api/summary
- 迁移：alembic upgrade head（先确认.env连本地）
- 前端：cd frontend && npm run build
- UFW：对外 ufw allow <port>/tcp（zheyang 15000-19999；3306禁开放）

## 9. 已知坑点(必读)
1. 后端无--reload：改代码不重启=不生效(404/旧引擎)。建议加--reload --reload-dir backend
2. BackgroundTasks不持久：筛选/AI跑批进程重启就中断,layer_status卡running。AI跑批途中别重启后端。
   失败现显示failed让用户重跑。→应迁持久化队列(Celery/RQ)
3. 前端状态以run.status为准,不要只看layer_status(旧run残留running)
4. AI必须独立DB session(_run_layer_ai已隔离),否则污染漏斗主session
5. 新旧引擎并存：现行funnel_v2.py；旧Q/R/V+ScreenConfig/ScreenResults标deprecated。
   旧run数据(无rejected_at_layer/layer_results)funnel端点有兼容防护但详情不完整,建议重跑
6. as_of_date默认2025-12-31,点时严格(取≤as_of且accepted_date≤as_of)
7. 数据时效：指标上限受compute.py year_range(2025)+fact是否拉到该财年双重限制
8. 负营运资本公司roce=None正常(Q5)
9. A股无新闻(Polygon仅美股),A股AI靠filing+人工兜底
10. AI成本：full每家~2.5s,大池几分钟；分层gate已只对存活公司调AI

## 10. 开发指南
- 测试：python -m pytest backend/tests/ -q
- 改筛选逻辑→funnel_v2.py+_eval_*,重启后端
- 加reason_code→reason_codes.py+reason_labels.py同步
- 改AI prompt→ai/prompts/*+bump version.py
- 加字段→改model→alembic revision写迁移(加列)→upgrade head→重启
- 加API→api/*.py+schemas/v2.py+api/index.js；加前端页→views/*.vue+router+App.vue
- 验证：改后端 python -c "import backend.main"；改前端 npm run build；
  查DB跨事务读最新前 db.rollback()(MySQL REPEATABLE READ)

## 11. 演进与文档索引
V1 30因子加权(废弃) | V2.0(2026-05) 三层Q/R/V+AI+回测生产可用 |
V2.1(2026-06) 重构ROCE→稳健→风险+分层gate+可配ROCE年数+AI介入选项+我的股票池+详情页瘦身
文档地图：prd/v2.0/Darwen_V2_PRD_Master.md(权威) docs/data-source-spec.md(数据源)
.agent/workflows/v2-implementation-roadmap.md(路线图) milestones/progress.md(进度)
milestones/2026-06-18.md(重构) milestones/2026-06-19.md(AI选项+bug修复+数据到2025)

## 12. 待办(截至2026-06-19)
- [ ] 数据到2025收尾：已扩year_range→2025/重算；需重拉FY2025财报(SEC backfill+Tushare全量)
      →再persist_all_metrics_bulk重算→重启验证(当前库内FY2025仅~31家美股齐/A股0家)
- [ ] AI真实调用端到端验收(需绑key)
- [ ] BackgroundTasks→持久化队列(解决跑批中断卡死)
- [ ] compute.py year_range上限改动态(免每年手改)
