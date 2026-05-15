<template>
  <div class="page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="detail">
      <!-- 1. 结论摘要 -->
      <header class="hdr">
        <h1>{{ detail.name }} <span class="ticker">{{ detail.ticker || '-' }}</span></h1>
        <div class="muted">{{ detail.market }} · {{ detail.industry_name || '-' }} · {{ detail.instrument_type }}</div>
        <div class="status-row">
          <span class="status-badge" :class="bucketClass(detail.result.status)">{{ statusLabel(detail.result.status) }}</span>
          <span v-if="detail.result.q_strong_track" class="tag-strong">STRONG_TRACK_RECORD</span>
        </div>
        <div class="codes">
          <ReasonPill v-for="c in detail.result.reason_codes" :key="c" :code="c" />
        </div>
      </header>

      <!-- 1.5. 公司画像（优化3）-->
      <section v-if="profile" class="card profile">
        <h2>公司画像</h2>
        <p class="muted">{{ profile.business_summary }}</p>

        <div class="profile-grid">
          <div v-if="profile.strengths?.length" class="col strengths">
            <h3>✓ 优势</h3>
            <div v-for="(p, i) in profile.strengths" :key="i" class="point">
              <strong>{{ p.title }}</strong>
              <div class="desc">{{ p.desc }}</div>
              <div v-if="p.metric" class="evidence">
                依据 · {{ p.metric }} = <code>{{ p.value }}</code>
                <span v-if="p.period"> · {{ p.period }}</span>
              </div>
            </div>
          </div>

          <div v-if="profile.concerns?.length" class="col concerns">
            <h3>⚠ 隐忧</h3>
            <div v-for="(p, i) in profile.concerns" :key="i" class="point">
              <strong>{{ p.title }}</strong>
              <div class="desc">{{ p.desc }}</div>
              <div v-if="p.metric" class="evidence">
                依据 · {{ p.metric }} = <code>{{ p.value }}</code>
                <span v-if="p.period"> · {{ p.period }}</span>
              </div>
            </div>
          </div>

          <div v-if="profile.neutral?.length" class="col neutral">
            <h3>• 中性</h3>
            <div v-for="(p, i) in profile.neutral" :key="i" class="point">
              <strong>{{ p.title }}</strong>
              <div class="desc">{{ p.desc }}</div>
              <div v-if="p.metric" class="evidence">
                依据 · {{ p.metric }} = <code>{{ p.value }}</code>
                <span v-if="p.period"> · {{ p.period }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. 核心指标 -->
      <section class="card">
        <h2>核心指标</h2>
        <div class="metrics-grid">
          <div class="metric">
            <div class="muted">ROCE 5Y 中位数</div>
            <div class="val">{{ fmtPct(detail.result.metrics_snapshot?.roce_5y_median) }}</div>
          </div>
          <div class="metric">
            <div class="muted">ROCE 10Y 中位数</div>
            <div class="val">{{ fmtPct(detail.result.metrics_snapshot?.roce_10y_median) }}</div>
          </div>
          <div class="metric">
            <div class="muted">PE_TTM</div>
            <div class="val">{{ fmtNum(detail.valuation_snapshot?.pe_ttm) }}x</div>
          </div>
          <div class="metric">
            <div class="muted">市值</div>
            <div class="val">{{ fmtMc(detail.valuation_snapshot?.market_cap) }}</div>
          </div>
          <div class="metric">
            <div class="muted">net_debt/EBIT</div>
            <div class="val">{{ fmtNum(detail.result.metrics_snapshot?.net_debt_ebit) }}</div>
          </div>
          <div class="metric">
            <div class="muted">利息保障倍数</div>
            <div class="val">{{ fmtNum(detail.result.metrics_snapshot?.interest_coverage) }}x</div>
          </div>
          <div class="metric">
            <div class="muted">CFO/NI 5Y 中位</div>
            <div class="val">{{ fmtNum(detail.result.metrics_snapshot?.median_cfo_ni_5y) }}</div>
          </div>
          <div class="metric">
            <div class="muted">股本 5Y CAGR</div>
            <div class="val">{{ fmtPct(detail.result.metrics_snapshot?.share_count_cagr_5y) }}</div>
          </div>
        </div>
      </section>

      <!-- 3. ROCE 时序（含财报下载 - 优化4）-->
      <section class="card">
        <h2>ROCE 年序列</h2>
        <table class="series">
          <thead>
            <tr>
              <th>财年末</th><th>ROCE</th><th>EBIT (B)</th>
              <th>CapitalEmployed (B)</th><th>NetPPE (B)</th>
              <th v-if="detail.market === 'US'">财报</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in detail.roce_series" :key="r.period_end">
              <td>{{ r.period_end }}</td>
              <td>{{ fmtPct(r.roce) }}</td>
              <td>{{ fmtBn(r.ebit) }}</td>
              <td>{{ fmtBn(r.capital_employed) }}</td>
              <td>{{ fmtBn(r.net_ppe) }}</td>
              <td v-if="detail.market === 'US'">
                <a class="filing-link" :href="filingUrl(detail.company_id, periodYear(r.period_end), '10-K')"
                   target="_blank" rel="noopener" title="打开 SEC EDGAR 原文">
                  📄 10-K
                </a>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="detail.market === 'CN_A'" class="muted small">
          A 股年报下载链接由 Tushare 接口暂无原文 URL，待后续补充。可访问 巨潮资讯网 (cninfo.com.cn) 自行查询。
        </p>
      </section>

      <!-- 4. 杠杆 + 现金质量 -->
      <section class="card two-cols">
        <div>
          <h3>杠杆指标</h3>
          <table class="series small">
            <thead><tr><th>财年末</th><th>net_debt/EBIT</th><th>利息保障</th><th>流动比</th></tr></thead>
            <tbody>
              <tr v-for="r in detail.leverage_series" :key="r.period_end">
                <td>{{ r.period_end }}</td>
                <td>{{ fmtNum(r.net_debt_ebit) }}</td>
                <td>{{ fmtNum(r.interest_coverage) }}x</td>
                <td>{{ fmtNum(r.current_ratio) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>现金质量</h3>
          <table class="series small">
            <thead><tr><th>财年末</th><th>CFO/NI</th><th>FCF (B)</th></tr></thead>
            <tbody>
              <tr v-for="r in detail.cash_quality_series" :key="r.period_end">
                <td>{{ r.period_end }}</td>
                <td>{{ fmtNum(r.cfo_ni_ratio) }}</td>
                <td>{{ fmtBn(r.fcf) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 5. AI 风险标签 -->
      <section v-if="detail.ai_result" class="card">
        <h2>AI 风险层</h2>
        <div class="muted">
          {{ detail.ai_result.ai_provider }} · {{ detail.ai_result.model_name }} ·
          prompt_version={{ detail.ai_result.prompt_version }} ·
          延迟 {{ detail.ai_result.latency_ms }}ms
        </div>
        <p>{{ detail.ai_result.summary_cn || '（无 summary）' }}</p>
        <div v-if="detail.ai_result.labels?.length">
          <h4>识别的风险标签：</h4>
          <ul>
            <li v-for="lbl in detail.ai_result.labels" :key="lbl.label">
              <strong>{{ lbl.label }}</strong>
              <span class="sev" :class="lbl.severity">{{ lbl.severity }}</span>
              · 置信度 {{ (lbl.confidence * 100).toFixed(0) }}%
              <div class="muted">{{ lbl.short_reason }}</div>
              <div class="evidence" v-if="lbl.evidence_doc_ids?.length">
                证据：<code v-for="e in lbl.evidence_doc_ids" :key="e">{{ e }}</code>
              </div>
            </li>
          </ul>
        </div>
      </section>
      <section v-else class="card muted">
        AI 风险层未启用或调用失败（screen_result.r_action={{ detail.result.r_action }}）。
      </section>

      <!-- 5.5. AI 分析提示词（优化5）-->
      <section v-if="analysisPrompt" class="card prompt-card">
        <h2>🤖 复制到 AI 深度分析</h2>
        <p class="muted">
          把下方提示词粘贴到 ChatGPT / Claude / Gemini，附上财报 PDF（点上方 ROCE 表"10-K"打开 SEC 原文）一起发，
          即可获得按 Pulak 方法论的深度分析。
        </p>
        <pre class="prompt-text">{{ analysisPrompt }}</pre>
        <div class="prompt-actions">
          <button class="btn-copy" @click="copyPrompt">
            {{ copied ? '✓ 已复制' : '📋 一键复制' }}
          </button>
          <span class="muted small">长度 {{ analysisPrompt.length }} 字符</span>
        </div>
      </section>

      <!-- 6. 字段血缘抽屉 -->
      <section class="card">
        <h2 @click="lineageOpen = !lineageOpen" class="clickable">
          字段血缘 ({{ detail.lineage?.length || 0 }} 条) {{ lineageOpen ? '▼' : '▶' }}
        </h2>
        <table v-if="lineageOpen" class="series small">
          <thead>
            <tr><th>字段</th><th>source</th><th>fact_id</th><th>period_end</th><th>effective_date</th><th>raw_value</th><th>公式版本</th></tr>
          </thead>
          <tbody>
            <tr v-for="(l, i) in detail.lineage.slice(0, 80)" :key="i">
              <td>{{ l.field_name }}</td>
              <td>{{ l.source_code }}</td>
              <td><code>{{ l.source_record_key?.slice(0, 12) || '-' }}</code></td>
              <td>{{ l.period_end }}</td>
              <td>{{ l.effective_date || '-' }}</td>
              <td>{{ fmtBn(l.raw_value) }}</td>
              <td>{{ l.formula_version }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getCompanyDetail, getCompanyProfile, getAnalysisPrompt, filingUrl } from '../api'
import { ensureReasonLabels } from '../composables/useReasonLabels'
import ReasonPill from '../components/ReasonPill.vue'

const route = useRoute()
const runId = Number(route.params.runId)
const companyId = route.params.companyId

const detail = ref(null)
const profile = ref(null)
const analysisPrompt = ref('')
const copied = ref(false)
const loading = ref(true)
const error = ref('')
const lineageOpen = ref(false)

function periodYear(periodEnd) {
  // "2024-09-28" → 2024
  return parseInt(String(periodEnd).slice(0, 4), 10)
}

async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(analysisPrompt.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = analysisPrompt.value
    document.body.appendChild(ta); ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}

function fmtPct(v) { return v == null ? '-' : (v * 100).toFixed(1) + '%' }
function fmtNum(v) { return v == null ? '-' : Number(v).toFixed(2) }
function fmtBn(v) {
  if (v == null) return '-'
  return (v / 1e9).toFixed(1) + 'B'
}
function fmtMc(v) {
  if (v == null) return '-'
  if (v > 1e12) return (v / 1e12).toFixed(2) + 'T'
  return (v / 1e9).toFixed(1) + 'B'
}

function statusLabel(s) {
  return ({
    HighConviction: '高确信候选',
    NearFairPrice: '接近合理价',
    TooExpensive: '太贵',
    Review: '人工覆核',
    Rejected: '排除',
  }[s]) || s
}
function bucketClass(s) {
  return ({
    HighConviction: 'green',
    NearFairPrice: 'blue',
    TooExpensive: 'yellow',
    Review: 'orange',
    Rejected: 'red',
  }[s])
}

onMounted(async () => {
  await ensureReasonLabels()
  try {
    const { data } = await getCompanyDetail(runId, companyId)
    detail.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
  // 并行加载画像 + 分析提示词（失败不阻塞主页面）
  getCompanyProfile(companyId).then(r => { profile.value = r.data }).catch(() => {})
  getAnalysisPrompt(companyId, runId).then(r => { analysisPrompt.value = r.data.prompt }).catch(() => {})
})
</script>

<style scoped>
.page { padding: 24px; max-width: 1080px; margin: 0 auto; }
.hdr h1 { margin: 0; display: flex; align-items: baseline; gap: 12px; }
.ticker { font-size: 1rem; color: #8888a0; font-family: ui-monospace, Menlo, monospace; }
.muted { color: #8888a0; font-size: 0.9rem; margin-top: 4px; }
.status-row { margin: 12px 0; display: flex; gap: 10px; align-items: center; }
.status-badge { padding: 4px 12px; border-radius: 14px; font-weight: 600; font-size: 0.85rem; }
.status-badge.green { background: #d6f5e0; color: #176b3a; }
.status-badge.blue { background: #d6e7f5; color: #1768b0; }
.status-badge.yellow { background: #fff4d6; color: #b06000; }
.status-badge.orange { background: #ffe4cc; color: #b04000; }
.status-badge.red { background: #fde0e0; color: #c00; }
.tag-strong { background: #4285f4; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
.codes { margin-top: 8px; }
.code-pill {
  display: inline-block; padding: 2px 8px; margin: 2px;
  background: #f0f0f5; border-radius: 4px; font-size: 0.75rem; color: #555;
}
.card { padding: 18px; border: 1px solid #e0e0e8; border-radius: 10px; background: #fff; margin: 16px 0; }
.card h2, .card h3 { margin: 0 0 12px 0; }
.two-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.metric { padding: 10px; background: #fafafd; border-radius: 8px; }
.metric .val { font-size: 1.2rem; font-weight: 600; margin-top: 4px; }
table.series { width: 100%; border-collapse: collapse; }
table.series th, table.series td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #f0f0f5; font-size: 0.85rem; }
table.series th { background: #fafafd; color: #555; }
.small td, .small th { padding: 4px 8px; font-size: 0.8rem; }
.sev { font-size: 0.75rem; padding: 1px 6px; margin: 0 4px; border-radius: 4px; }
.sev.low { background: #fff4d6; color: #b06000; }
.sev.medium { background: #ffe4cc; color: #b04000; }
.sev.high { background: #fde0e0; color: #c00; }
.evidence code { background: #f0f0f5; padding: 1px 4px; margin: 0 2px; font-size: 0.75rem; }
.clickable { cursor: pointer; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }

/* 公司画像（优化3）*/
.profile h3 { margin: 0 0 10px 0; font-size: 1.0rem; }
.profile-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-top: 12px; }
.profile-grid .col { padding: 12px; border-radius: 8px; }
.profile-grid .strengths { background: #f0faf3; border-left: 3px solid #34a853; }
.profile-grid .concerns { background: #fef0e6; border-left: 3px solid #ea4335; }
.profile-grid .neutral { background: #f5f5f7; border-left: 3px solid #888; }
.profile-grid .strengths h3 { color: #176b3a; }
.profile-grid .concerns h3 { color: #b30000; }
.profile-grid .neutral h3 { color: #555; }
.profile-grid .point { margin: 10px 0; padding-bottom: 10px; border-bottom: 1px dashed rgba(0,0,0,0.08); }
.profile-grid .point:last-child { border-bottom: none; }
.profile-grid .point strong { font-size: 0.9rem; }
.profile-grid .point .desc { margin: 4px 0; font-size: 0.85rem; color: #333; line-height: 1.5; }
.profile-grid .evidence { font-size: 0.75rem; color: #666; }
.profile-grid .evidence code { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 3px; }

/* 财报下载链接（优化4）*/
.filing-link {
  display: inline-block; padding: 2px 8px; background: #eef3fc;
  color: #1f3a8a; border-radius: 4px; text-decoration: none; font-size: 0.78rem;
}
.filing-link:hover { background: #d6e7f5; }
.series .small { font-size: 0.8rem; color: #8888a0; margin-top: 8px; }

/* AI 提示词卡（优化5）*/
.prompt-card pre.prompt-text {
  max-height: 400px; overflow-y: auto;
  padding: 14px; background: #fafafd; border: 1px solid #e0e0e8; border-radius: 6px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.82rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
}
.prompt-actions { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.btn-copy {
  padding: 8px 18px; border-radius: 6px;
  background: #4285f4; color: #fff; border: none; cursor: pointer; font-size: 0.9rem;
}
.btn-copy:hover { background: #1a73e8; }
.small { font-size: 0.8rem; }
</style>
