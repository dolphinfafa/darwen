<template>
  <div class="page">
    <header class="hd">
      <h1>筛选漏斗 · Run #{{ runId }}</h1>
      <div class="muted" v-if="status">
        {{ status.universe_name }} · {{ status.market }} · 共 {{ status.total_count }} 家 ·
        as_of {{ status.as_of_date }}
        <span :class="['st', runStateClass]">{{ runStateText }}</span>
      </div>
    </header>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="isFailed" class="error">
      ⚠ 本次筛选执行中断（{{ status?.error_msg || 'AI 调用或后台任务被中断' }}）。
      多为 AI 跑批途中后端重启所致，请返回<router-link to="/universe">重新发起筛选</router-link>。
    </div>

    <!-- 当前层评估进度 -->
    <div v-if="isRunning" class="running">
      <strong>{{ layerLabel(status.current_layer) }}</strong> 评估中…
      {{ status.progress_count }}/{{ status.total_count }}
      <div class="bar"><div class="fill" :style="{ width: runningPct + '%' }"></div></div>
      <div v-if="status.current_company_name" class="cur">🔍 {{ status.current_company_name }}</div>
    </div>

    <!-- 搜索 + 过滤栏 -->
    <div v-if="funnel" class="filters">
      <input v-model="q" class="search" placeholder="搜索代码 / 名称…" />
      <select v-model="fGroup">
        <option value="">全部结果</option>
        <option v-for="g in GROUPS" :key="g.key" :value="g.key">{{ g.label }}</option>
      </select>
      <select v-model="fMarket">
        <option value="">全部市场</option>
        <option v-for="m in markets" :key="m" :value="m">{{ m }}</option>
      </select>
      <select v-model="fIndustry">
        <option value="">全部行业</option>
        <option v-for="ind in industries" :key="ind" :value="ind">{{ ind }}</option>
      </select>
      <button v-if="hasFilter" class="clear" @click="clearFilters">清空筛选</button>
      <span class="match">匹配 <b>{{ filtered.length }}</b> / {{ allRows.length }}</span>
    </div>

    <!-- 三层手风琴 + 最终入选 -->
    <div v-if="funnel" class="acc">
      <div v-for="g in visibleGroups" :key="g.key" class="panel" :class="{ open: isOpen(g.key) }">
        <div class="panel-hd" @click="toggle(g.key)">
          <span class="caret">{{ isOpen(g.key) ? '▼' : '▶' }}</span>
          <strong :class="{ surv: g.key === 'survivor' }">{{ g.label }}</strong>
          <span v-if="meta(g.key)" class="state">{{ stateText(meta(g.key).state) }}</span>
          <span class="cnt" v-if="meta(g.key)">
            <template v-if="g.key !== 'survivor'">
              {{ meta(g.key).input }} 进 → <b>{{ meta(g.key).passed }}</b> 过 · 过滤 <b class="rej">{{ meta(g.key).rejected }}</b>
            </template>
            <template v-else><b class="ok">{{ meta(g.key).passed }}</b> 家入选</template>
          </span>
          <span class="mtag">匹配 {{ rowsOf(g.key).length }}</span>
        </div>
        <table v-if="isOpen(g.key)" class="rows">
          <tbody>
            <tr v-for="c in rowsOf(g.key)" :key="c.company_id" @click="goDetail(c.company_id)">
              <td class="tk"><code>{{ c.ticker || '-' }}</code></td>
              <td class="nm">{{ c.name }}</td>
              <td class="mk"><span class="market" :class="c.market.toLowerCase()">{{ c.market }}</span></td>
              <td class="ind">{{ c.industry_name || '-' }}</td>
              <td v-if="g.key === 'survivor'" class="mt">
                ROCE {{ fmtPct(c.metrics_snapshot?.roce_median ?? c.metrics_snapshot?.roce_5y_median) }}
              </td>
              <td v-else class="codes"><ReasonPill v-for="rc in c.reason_codes" :key="rc" :code="rc" /></td>
            </tr>
            <tr v-if="!rowsOf(g.key).length"><td colspan="5" class="empty">无匹配股票</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScreenRunStatus, getFunnel } from '../api'
import { ensureReasonLabels } from '../composables/useReasonLabels'
import ReasonPill from '../components/ReasonPill.vue'

const route = useRoute()
const router = useRouter()
const runId = Number(route.params.runId)
const status = ref(null)
const funnel = ref(null)
const error = ref('')
let timer = null

const GROUPS = [
  { key: 'roce', label: 'ROCE 门槛' },
  { key: 'sturdiness', label: '稳健性筛选' },
  { key: 'risk', label: '风险性筛选' },
  { key: 'survivor', label: '最终入选' },
]
const LAYER_LABEL = { roce: 'ROCE 门槛', sturdiness: '稳健性筛选', risk: '风险性筛选', done: '已完成' }
function layerLabel(l) { return LAYER_LABEL[l] || l }
function stateText(s) {
  return ({ pending: '待处理', running: '评估中', awaiting_review: '待复核', completed: '已完成' }[s]) || s
}

const isRunning = computed(() => status.value?.layer_status === 'running')
const isFailed = computed(() => status.value?.status === 'failed' || status.value?.layer_status === 'failed')
const isDone = computed(() => status.value?.run_status === 'completed' || status.value?.status === 'completed')
const runStateText = computed(() => isDone.value ? '已完成' : (isFailed.value ? '失败' : (isRunning.value ? '运行中' : (status.value?.status || ''))))
const runStateClass = computed(() => isDone.value ? 'done' : (isFailed.value ? 'fail' : 'run'))
const runningPct = computed(() => {
  const t = status.value?.total_count || 0
  return t ? Math.min(100, Math.round(100 * (status.value.progress_count || 0) / t)) : 0
})
function fmtPct(v) { return v == null ? '-' : (v * 100).toFixed(1) + '%' }

// ───── 摊平 + 过滤 ─────
const q = ref('')
const fMarket = ref('')
const fGroup = ref('')
const fIndustry = ref('')

const allRows = computed(() => {
  const f = funnel.value
  if (!f) return []
  const out = []
  for (const ly of (f.layers || [])) for (const c of (ly.rejected || [])) out.push({ ...c, group: ly.layer })
  for (const c of (f.survivors || [])) out.push({ ...c, group: 'survivor' })
  return out
})
const markets = computed(() => [...new Set(allRows.value.map(r => r.market).filter(Boolean))])
const industries = computed(() => [...new Set(allRows.value.map(r => r.industry_name).filter(Boolean))].sort())
const hasFilter = computed(() => !!(q.value || fMarket.value || fGroup.value || fIndustry.value))

const filtered = computed(() => {
  const kw = q.value.trim().toLowerCase()
  return allRows.value.filter(r => {
    if (kw && !((r.ticker || '').toLowerCase().includes(kw) || (r.name || '').toLowerCase().includes(kw))) return false
    if (fMarket.value && r.market !== fMarket.value) return false
    if (fGroup.value && r.group !== fGroup.value) return false
    if (fIndustry.value && (r.industry_name || '') !== fIndustry.value) return false
    return true
  })
})
function rowsOf(g) { return filtered.value.filter(r => r.group === g) }
function meta(g) {
  const f = funnel.value
  if (!f) return null
  if (g === 'survivor') return { passed: (f.survivors || []).length, state: 'completed' }
  const ly = (f.layers || []).find(l => l.layer === g)
  return ly ? { input: ly.input_count, passed: ly.passed_count, rejected: ly.rejected_count, state: ly.state } : null
}
const visibleGroups = computed(() => fGroup.value ? GROUPS.filter(g => g.key === fGroup.value) : GROUPS)

// 折叠：默认入选展开、三层折叠；有筛选时自动展开有匹配的面板
const open = ref({ roce: false, sturdiness: false, risk: false, survivor: true })
function toggle(g) { open.value[g] = !open.value[g] }
function isOpen(g) { return hasFilter.value ? rowsOf(g).length > 0 : open.value[g] }
function clearFilters() { q.value = ''; fMarket.value = ''; fGroup.value = ''; fIndustry.value = '' }

function goDetail(cid) {
  router.push({ name: 'CompanyDetailV2', params: { runId, companyId: cid } })
}

async function refresh() {
  try {
    const [{ data: s }, { data: f }] = await Promise.all([
      getScreenRunStatus(runId), getFunnel(runId),
    ])
    status.value = s
    funnel.value = f
    if (s.layer_status !== 'running') stop()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
    stop()
  }
}
function start() { if (!timer) timer = setInterval(refresh, 1500) }
function stop() { if (timer) { clearInterval(timer); timer = null } }

onMounted(async () => {
  await ensureReasonLabels()
  await refresh()
  if (status.value?.layer_status === 'running') start()
})
onUnmounted(stop)
</script>

<style scoped>
.page { padding: 24px; max-width: 1100px; margin: 0 auto; }
.hd h1 { margin-bottom: 4px; }
.muted { color: #8888a0; font-size: 0.9rem; }
.st { margin-left: 10px; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
.st.done { background: #d6f5e0; color: #176b3a; }
.st.run { background: #d6e7f5; color: #1768b0; }
.st.fail { background: #fde0e0; color: #c00; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; margin: 12px 0; }

.running { margin: 16px 0; padding: 14px; border: 1px solid #d6e7f5; background: #f5f9ff; border-radius: 10px; }
.running .bar { height: 8px; background: #e6eef7; border-radius: 4px; overflow: hidden; margin-top: 8px; }
.running .fill { height: 100%; background: #4285f4; transition: width .3s; }
.running .cur { margin-top: 6px; font-size: 0.85rem; color: #1a3a8a; }

/* 过滤栏 */
.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 16px 0 12px; }
.filters .search { flex: 1; min-width: 180px; padding: 7px 12px; border: 1px solid #d6dae3; border-radius: 8px; font-size: 0.9rem; }
.filters select { padding: 7px 10px; border: 1px solid #d6dae3; border-radius: 8px; font-size: 0.88rem; background: #fff; }
.filters .clear { padding: 6px 12px; border: 1px solid #f0caca; background: #fff; color: #c0392b; border-radius: 8px; cursor: pointer; font-size: 0.85rem; }
.filters .match { margin-left: auto; font-size: 0.85rem; color: #8888a0; }
.filters .match b { color: #1a3a8a; }

/* 手风琴 */
.acc { display: flex; flex-direction: column; gap: 10px; }
.panel { border: 1px solid #e0e0e8; border-radius: 10px; background: #fff; overflow: hidden; }
.panel.open { border-color: #c9d4e6; }
.panel-hd { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; flex-wrap: wrap; user-select: none; }
.panel-hd:hover { background: #f7f9fc; }
.panel-hd .caret { color: #8888a0; font-size: 0.8rem; width: 14px; }
.panel-hd strong.surv { color: #176b3a; }
.panel-hd .state { font-size: 0.72rem; padding: 1px 8px; border-radius: 8px; background: #f0f0f5; color: #666; }
.panel-hd .cnt { font-size: 0.85rem; color: #555; }
.panel-hd .cnt .rej { color: #c00; }
.panel-hd .cnt .ok { color: #176b3a; }
.panel-hd .mtag { margin-left: auto; font-size: 0.78rem; color: #8888a0; }

.rows { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.rows td { padding: 7px 16px; border-top: 1px solid #f3f3f7; }
.rows tbody tr { cursor: pointer; }
.rows tbody tr:hover { background: #f7f9fc; }
.rows .tk code { background: #f0f0f5; padding: 1px 6px; border-radius: 3px; }
.rows .nm { font-weight: 500; }
.market { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
.market.us { background: #d6e7f5; color: #1768b0; }
.market.cn_a { background: #fde0e0; color: #c00; }
.rows .ind { color: #666; font-size: 0.82rem; }
.rows .codes { max-width: 380px; }
.rows .mt { color: #176b3a; font-size: 0.82rem; text-align: right; }
.rows .empty { color: #aaa; text-align: center; padding: 14px; }
</style>
