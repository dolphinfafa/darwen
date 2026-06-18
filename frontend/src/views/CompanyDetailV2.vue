<template>
  <div class="page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="detail">
      <!-- 头部：结论 + 入池 -->
      <header class="hdr">
        <div class="title-row">
          <h1>{{ detail.name }} <span class="ticker">{{ detail.ticker || '-' }}</span></h1>
          <button class="btn-add" @click="openAdd">➕ 进入我的股票池</button>
        </div>
        <div class="muted">{{ detail.market }} · {{ detail.industry_name || '-' }} · {{ detail.instrument_type }}</div>
        <div class="status-row">
          <span class="result-badge" :class="resultClass">{{ resultText }}</span>
          <span v-if="detail.result.q_strong_track" class="tag-strong">10Y 强通过</span>
        </div>
        <div class="codes"><ReasonPill v-for="c in detail.result.reason_codes" :key="c" :code="c" /></div>

        <!-- 入池面板 -->
        <div v-if="showAdd" class="add-panel">
          <div class="add-row">
            <select v-model="addTarget">
              <option value="">＋ 新建股票池…</option>
              <option v-for="w in watchlists" :key="w.id" :value="w.id">{{ w.name }}（{{ w.item_count }}）</option>
            </select>
            <input v-if="!addTarget" v-model="newWlName" placeholder="新池名称（默认：我的股票池）" />
            <button class="btn" :disabled="adding" @click="confirmAdd">{{ adding ? '...' : '确定加入' }}</button>
            <button class="btn ghost" @click="showAdd = false">取消</button>
          </div>
          <div v-if="addMsg" class="add-msg">{{ addMsg }}</div>
        </div>
      </header>

      <!-- 历史 ROCE（含出处：10-K 原文）-->
      <section class="card">
        <h2>历史 ROCE</h2>
        <table class="series">
          <thead>
            <tr>
              <th>财年末</th><th>ROCE</th><th>EBIT</th><th>CapitalEmployed</th>
              <th>出处</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in detail.roce_series" :key="r.period_end">
              <td>{{ r.period_end }}</td>
              <td :class="{ ok: r.roce >= 0.2 }">{{ fmtPct(r.roce) }}</td>
              <td>{{ fmtBn(r.ebit) }}</td>
              <td>{{ fmtBn(r.capital_employed) }}</td>
              <td>
                <a v-if="detail.market === 'US'" class="src" :href="filingUrl(detail.company_id, periodYear(r.period_end), '10-K')"
                   target="_blank" rel="noopener" title="SEC EDGAR 10-K 原文">📄 10-K</a>
                <span v-else class="muted small">巨潮资讯网</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="muted small">ROCE 数据来源：{{ detail.market === 'US' ? 'SEC EDGAR XBRL' : 'Tushare 财报' }}（按 roce_v1 口径计算，逐年财报值）。</p>
      </section>

      <!-- 过滤原因与依据（三层）-->
      <section class="card">
        <h2>筛选过程与过滤原因</h2>
        <div v-for="L in LAYERS" :key="L.key" class="layer-block" :class="layerState(L.key)">
          <div class="layer-row">
            <strong>{{ L.label }}</strong>
            <span class="lstate">{{ layerStateText(L.key) }}</span>
          </div>
          <!-- 稳健层：原则明细 -->
          <ul v-if="layerData(L.key)?.principles" class="principles">
            <li v-for="(p, name) in layerData(L.key).principles" :key="name" :class="p.status">
              <span class="pname">{{ principleLabel(name) }}</span>
              <span class="pstatus">{{ pstatusText(p.status) }}</span>
              <span v-if="p.reason" class="preason">{{ p.reason }}</span>
              <template v-if="p.evidence_doc_ids?.length">
                · 出处：
                <a v-for="d in p.evidence_doc_ids" :key="d" class="src" :href="evUrl(d)" target="_blank" rel="noopener">{{ evTitle(d) }}</a>
              </template>
            </li>
          </ul>
          <!-- 该层 reason codes -->
          <div v-if="layerData(L.key)?.reason_codes?.length" class="codes">
            <ReasonPill v-for="c in layerData(L.key).reason_codes" :key="c" :code="c" />
          </div>
          <div v-if="!layerData(L.key)" class="muted small">未进入此层。</div>
        </div>

        <!-- 风险层 AI 摘要 -->
        <div v-if="detail.ai_result" class="ai-summary">
          <h4>AI 风险摘要</h4>
          <p class="muted">{{ detail.ai_result.summary_cn || '（无）' }}</p>
          <ul v-if="detail.ai_result.labels?.length" class="ai-labels">
            <li v-for="lbl in detail.ai_result.labels" :key="lbl.label">
              <strong>{{ lbl.label }}</strong>
              <span class="sev" :class="lbl.severity">{{ lbl.severity }}</span>
              · {{ lbl.short_reason }}
              <template v-if="lbl.evidence_doc_ids?.length">
                · 出处：<a v-for="d in lbl.evidence_doc_ids" :key="d" class="src" :href="evUrl(d)" target="_blank" rel="noopener">{{ evTitle(d) }}</a>
              </template>
            </li>
          </ul>
        </div>
      </section>

      <!-- 数据血缘（出处溯源，折叠）-->
      <section class="card">
        <h2 class="clickable" @click="lineageOpen = !lineageOpen">
          数据出处溯源（{{ detail.lineage?.length || 0 }} 条）{{ lineageOpen ? '▼' : '▶' }}
        </h2>
        <table v-if="lineageOpen" class="series small">
          <thead><tr><th>字段</th><th>来源</th><th>fact_id</th><th>period_end</th><th>原值</th><th>公式版本</th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in detail.lineage.slice(0, 80)" :key="i">
              <td>{{ l.field_name }}</td><td>{{ l.source_code }}</td>
              <td><code>{{ l.source_record_key?.slice(0, 12) || '-' }}</code></td>
              <td>{{ l.period_end }}</td><td>{{ fmtBn(l.raw_value) }}</td><td>{{ l.formula_version }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getCompanyDetail, filingUrl, getEvidence, getWatchlists, addToWatchlist } from '../api'
import { ensureReasonLabels } from '../composables/useReasonLabels'
import ReasonPill from '../components/ReasonPill.vue'

const route = useRoute()
const runId = Number(route.params.runId)
const companyId = route.params.companyId

const detail = ref(null)
const loading = ref(true)
const error = ref('')
const lineageOpen = ref(false)
const evidence = ref({})  // doc_id -> {title, url, ...}

// 入池
const showAdd = ref(false)
const watchlists = ref([])
const addTarget = ref('')
const newWlName = ref('')
const adding = ref(false)
const addMsg = ref('')

const LAYERS = [
  { key: 'roce', label: '① ROCE 门槛' },
  { key: 'sturdiness', label: '② 稳健性筛选' },
  { key: 'risk', label: '③ 风险性筛选' },
]
const PRINCIPLE_LABEL = {
  no_debt_strong_cashflow: '无负债·有现金流', diversified_customers: '多元化客户',
  high_moat: '竞争壁垒', diversified_suppliers: '多元化供应商',
  stable_management: '稳定管理团队', slow_changing_industry: '行业变化慢',
}

function periodYear(p) { return parseInt(String(p).slice(0, 4), 10) }
function fmtPct(v) { return v == null ? '-' : (v * 100).toFixed(1) + '%' }
function fmtBn(v) { return v == null ? '-' : (Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : (v / 1e6).toFixed(1) + 'M') }

function layerData(k) { return detail.value?.layer_results?.[k] || null }
function layerState(k) {
  const d = layerData(k)
  if (!d) return 'skip'
  return detail.value.rejected_at_layer === k ? 'failed' : 'passed'
}
function layerStateText(k) {
  const d = layerData(k)
  if (!d) return '未进入'
  return detail.value.rejected_at_layer === k ? '✕ 在此层被过滤' : '✓ 通过'
}
function principleLabel(n) { return PRINCIPLE_LABEL[n] || n }
function pstatusText(s) { return ({ pass: '✓', fail: '✕', pending_ai: '待AI' }[s]) || s }
function evUrl(d) { return evidence.value[d]?.url || '#' }
function evTitle(d) { return evidence.value[d]?.title || d }

const resultText = computed(() => {
  const r = detail.value?.rejected_at_layer
  if (!r) return detail.value?.result?.status === 'Rejected' ? '✕ 已排除' : '✅ 入选（通过三层）'
  return { roce: '✕ ROCE 门槛被过滤', sturdiness: '✕ 稳健性筛选被过滤', risk: '✕ 风险性筛选被过滤' }[r] || '✕ 已过滤'
})
const resultClass = computed(() => detail.value?.rejected_at_layer ? 'red' : 'green')

function collectDocIds(d) {
  const ids = new Set()
  for (const layer of Object.values(d.layer_results || {})) {
    for (const p of Object.values(layer.principles || {})) {
      (p.evidence_doc_ids || []).forEach(x => ids.add(x))
    }
  }
  (d.ai_result?.labels || []).forEach(l => (l.evidence_doc_ids || []).forEach(x => ids.add(x)))
  return [...ids]
}

async function openAdd() {
  showAdd.value = true; addMsg.value = ''
  try { const { data } = await getWatchlists(); watchlists.value = data } catch {}
}
async function confirmAdd() {
  adding.value = true; addMsg.value = ''
  try {
    const body = { company_id: companyId, source_run_id: runId }
    if (addTarget.value) body.watchlist_id = addTarget.value
    else body.watchlist_name = newWlName.value.trim() || '我的股票池'
    const { data } = await addToWatchlist(body)
    addMsg.value = `已加入「${data.name}」（共 ${data.item_count} 只）`
  } catch (e) {
    addMsg.value = '加入失败：' + (e.response?.data?.detail || e.message)
  } finally { adding.value = false }
}

onMounted(async () => {
  await ensureReasonLabels()
  try {
    const { data } = await getCompanyDetail(runId, companyId)
    detail.value = data
    const ids = collectDocIds(data)
    if (ids.length) {
      getEvidence(companyId, ids.join(',')).then(r => {
        const map = {}; r.data.forEach(e => { map[e.doc_id] = e }); evidence.value = map
      }).catch(() => {})
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 24px; max-width: 980px; margin: 0 auto; }
.muted { color: #8888a0; font-size: 0.9rem; }
.small { font-size: 0.8rem; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }
.hdr { margin-bottom: 8px; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.hdr h1 { margin: 0; display: flex; align-items: baseline; gap: 12px; }
.ticker { font-size: 1rem; color: #8888a0; font-family: ui-monospace, Menlo, monospace; }
.btn-add { padding: 8px 16px; border: none; border-radius: 8px; background: #4285f4; color: #fff; cursor: pointer; white-space: nowrap; }
.status-row { margin: 12px 0; display: flex; gap: 10px; align-items: center; }
.result-badge { padding: 4px 14px; border-radius: 14px; font-weight: 600; font-size: 0.9rem; }
.result-badge.green { background: #d6f5e0; color: #176b3a; }
.result-badge.red { background: #fde0e0; color: #c00; }
.tag-strong { background: #4285f4; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
.codes { margin-top: 8px; }
.add-panel { margin-top: 12px; padding: 12px; background: #f5f9ff; border: 1px solid #d6e7f5; border-radius: 8px; }
.add-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.add-row select, .add-row input { padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; }
.btn { padding: 6px 14px; border: 1px solid #4285f4; background: #4285f4; color: #fff; border-radius: 6px; cursor: pointer; }
.btn.ghost { background: #fff; color: #4285f4; }
.btn:disabled { opacity: .5; }
.add-msg { margin-top: 8px; font-size: 0.85rem; color: #176b3a; }
.card { padding: 18px; border: 1px solid #e0e0e8; border-radius: 10px; background: #fff; margin: 16px 0; }
.card h2 { margin: 0 0 12px 0; }
.clickable { cursor: pointer; }
table.series { width: 100%; border-collapse: collapse; }
table.series th, table.series td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #f0f0f5; font-size: 0.85rem; }
table.series th { background: #fafafd; color: #555; }
table.series td.ok { color: #176b3a; font-weight: 600; }
.src { display: inline-block; padding: 1px 6px; margin: 0 2px; background: #eef3fc; color: #1f3a8a; border-radius: 4px; text-decoration: none; font-size: 0.78rem; }
.src:hover { background: #d6e7f5; }
.layer-block { padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 3px solid #ccc; background: #fafafd; }
.layer-block.passed { border-left-color: #34a853; }
.layer-block.failed { border-left-color: #ea4335; background: #fef6f6; }
.layer-block.skip { opacity: 0.6; }
.layer-row { display: flex; gap: 10px; align-items: center; }
.lstate { font-size: 0.82rem; color: #666; }
.principles { list-style: none; padding: 0; margin: 8px 0 0; }
.principles li { padding: 4px 0; font-size: 0.85rem; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.principles li.fail .pstatus { color: #c00; }
.principles li.pass .pstatus { color: #176b3a; }
.principles .pname { min-width: 130px; font-weight: 500; }
.principles .preason { color: #555; }
.ai-summary { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #e0e0e8; }
.ai-summary h4 { margin: 0 0 6px; }
.ai-labels { margin: 6px 0 0; padding-left: 18px; font-size: 0.85rem; }
.sev { font-size: 0.72rem; padding: 1px 6px; border-radius: 4px; }
.sev.low { background: #fff4d6; color: #b06000; }
.sev.medium { background: #ffe4cc; color: #b04000; }
.sev.high { background: #fde0e0; color: #c00; }
</style>
