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

    <!-- 漏斗层 -->
    <div v-if="funnel" class="funnel">
      <div v-for="(ly, i) in funnel.layers" :key="ly.layer" class="layer" :class="ly.state">
        <div class="layer-hd">
          <span class="idx">{{ i + 1 }}</span>
          <strong>{{ ly.label }}</strong>
          <span class="state">{{ stateText(ly.state) }}</span>
          <span class="cnt">{{ ly.input_count }} 进 → <b>{{ ly.passed_count }}</b> 过 · 过滤 <b class="rej">{{ ly.rejected_count }}</b></span>
        </div>
        <div class="fbar">
          <div class="fpass" :style="{ width: barPct(ly) + '%' }"></div>
        </div>

        <table v-if="ly.rejected.length" class="rows">
          <tbody>
            <tr v-for="c in ly.rejected" :key="c.company_id" @click="goDetail(c.company_id)">
              <td class="tk"><code>{{ c.ticker || '-' }}</code></td>
              <td class="nm">{{ c.name }}<span v-if="c.manual_action" class="manual">人工</span></td>
              <td class="codes"><ReasonPill v-for="rc in c.reason_codes" :key="rc" :code="rc" /></td>
              <td class="op">
                <button v-if="canManage(ly)" class="link pass" @click.stop="doPass(c.company_id)">放行 →</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 当前层 gate：存活可剔除 + 推进 -->
    <div v-if="isAwaiting && funnel" class="gate">
      <h3>{{ layerLabel(status.current_layer) }} · 当前通过 {{ funnel.survivors.length }} 家
        <span class="muted">（可手动剔除后再推进）</span></h3>
      <table v-if="funnel.survivors.length" class="rows survivors">
        <tbody>
          <tr v-for="c in funnel.survivors" :key="c.company_id" @click="goDetail(c.company_id)">
            <td class="tk"><code>{{ c.ticker || '-' }}</code></td>
            <td class="nm">{{ c.name }}</td>
            <td class="mt">ROCE {{ fmtPct(c.metrics_snapshot?.roce_median ?? c.metrics_snapshot?.roce_5y_median) }}</td>
            <td class="op"><button class="link reject" @click.stop="doReject(c.company_id)">剔除 ✕</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">本层无存活公司。</div>
      <button class="advance" :disabled="advancing" @click="doAdvance">
        {{ advancing ? '处理中…' : advanceLabel }}
      </button>
    </div>

    <!-- 完成：最终入选 -->
    <div v-if="isDone && funnel" class="final">
      <h2>✅ 最终入选 {{ funnel.survivors.length }} 家</h2>
      <table v-if="funnel.survivors.length" class="rows survivors">
        <tbody>
          <tr v-for="c in funnel.survivors" :key="c.company_id" @click="goDetail(c.company_id)">
            <td class="tk"><code>{{ c.ticker || '-' }}</code></td>
            <td class="nm">{{ c.name }}</td>
            <td class="mt">ROCE {{ fmtPct(c.metrics_snapshot?.roce_median ?? c.metrics_snapshot?.roce_5y_median) }}</td>
            <td class="op"><button class="link" @click.stop="goDetail(c.company_id)">详情 →</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">无公司通过全部三层。</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScreenRunStatus, getFunnel, advanceLayer, manualAction } from '../api'
import { ensureReasonLabels } from '../composables/useReasonLabels'
import ReasonPill from '../components/ReasonPill.vue'

const route = useRoute()
const router = useRouter()
const runId = Number(route.params.runId)
const status = ref(null)
const funnel = ref(null)
const error = ref('')
const advancing = ref(false)
let timer = null

const LAYER_LABEL = { roce: 'ROCE 门槛', sturdiness: '稳健性筛选', risk: '风险性筛选', done: '已完成' }
function layerLabel(l) { return LAYER_LABEL[l] || l }
function stateText(s) {
  return ({ pending: '待处理', running: '评估中', awaiting_review: '待复核', completed: '已完成' }[s]) || s
}

const isRunning = computed(() => status.value?.layer_status === 'running')
const isAwaiting = computed(() => status.value?.layer_status === 'awaiting_review')
const isDone = computed(() => status.value?.run_status === 'completed' || status.value?.status === 'completed')
const runStateText = computed(() => isDone.value ? '已完成' : (isAwaiting.value ? '待复核' : (isRunning.value ? '运行中' : (status.value?.status || ''))))
const runStateClass = computed(() => isDone.value ? 'done' : (isAwaiting.value ? 'await' : 'run'))
const advanceLabel = computed(() => status.value?.current_layer === 'risk' ? '完成筛选 ✓' : '进入下一层 →')

const runningPct = computed(() => {
  const t = status.value?.total_count || 0
  return t ? Math.min(100, Math.round(100 * (status.value.progress_count || 0) / t)) : 0
})

function barPct(ly) {
  return ly.input_count ? Math.round(100 * ly.passed_count / ly.input_count) : 0
}
function canManage(ly) {
  return isAwaiting.value && ly.layer === status.value?.current_layer
}
function fmtPct(v) { return v == null ? '-' : (v * 100).toFixed(1) + '%' }

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
    // running 才需要持续轮询；awaiting/completed/failed 停止
    if (s.layer_status !== 'running') stop()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
    stop()
  }
}
function start() { if (!timer) timer = setInterval(refresh, 1500) }
function stop() { if (timer) { clearInterval(timer); timer = null } }

async function doAdvance() {
  advancing.value = true
  try {
    await advanceLayer(runId)
    await refresh()
    start()  // 下一层进入 running，恢复轮询
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    advancing.value = false
  }
}
async function doPass(cid) {
  try { await manualAction(runId, cid, 'force_pass'); await refresh() }
  catch (e) { error.value = e.response?.data?.detail || e.message }
}
async function doReject(cid) {
  try { await manualAction(runId, cid, 'force_reject'); await refresh() }
  catch (e) { error.value = e.response?.data?.detail || e.message }
}

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
.st.await { background: #fff4d6; color: #b06000; }
.st.run { background: #d6e7f5; color: #1768b0; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; margin: 12px 0; }

.running { margin: 16px 0; padding: 14px; border: 1px solid #d6e7f5; background: #f5f9ff; border-radius: 10px; }
.running .bar { height: 8px; background: #e6eef7; border-radius: 4px; overflow: hidden; margin-top: 8px; }
.running .fill { height: 100%; background: #4285f4; transition: width .3s; }
.running .cur { margin-top: 6px; font-size: 0.85rem; color: #1a3a8a; }

.funnel { margin-top: 16px; display: flex; flex-direction: column; gap: 14px; }
.layer { border: 1px solid #e0e0e8; border-radius: 10px; padding: 14px 16px; background: #fff; }
.layer.completed { border-color: #cfe8d8; }
.layer.awaiting_review { border-color: #f0d9a8; box-shadow: 0 0 0 2px #fff7e6; }
.layer.pending { opacity: 0.6; }
.layer-hd { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.idx { width: 22px; height: 22px; border-radius: 50%; background: #4285f4; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; }
.layer-hd .state { font-size: 0.75rem; padding: 1px 8px; border-radius: 8px; background: #f0f0f5; color: #666; }
.layer-hd .cnt { margin-left: auto; font-size: 0.85rem; color: #555; }
.layer-hd .cnt .rej { color: #c00; }
.fbar { height: 6px; background: #fde0e0; border-radius: 3px; overflow: hidden; margin: 10px 0; }
.fpass { height: 100%; background: #34a853; }

.rows { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 0.88rem; }
.rows td { padding: 6px 10px; border-bottom: 1px solid #f3f3f7; }
.rows tbody tr { cursor: pointer; }
.rows tbody tr:hover { background: #f7f9fc; }
.rows .tk code { background: #f0f0f5; padding: 1px 6px; border-radius: 3px; }
.rows .nm { font-weight: 500; }
.manual { margin-left: 6px; font-size: 0.7rem; background: #fff4d6; color: #b06000; padding: 1px 5px; border-radius: 4px; }
.rows .codes { max-width: 420px; }
.rows .op { text-align: right; white-space: nowrap; }
.survivors .mt { color: #176b3a; font-size: 0.82rem; }
.link { background: none; border: none; cursor: pointer; color: #4285f4; padding: 0; font-size: 0.85rem; }
.link.pass { color: #176b3a; }
.link.reject { color: #c00; }

.gate { margin-top: 20px; padding: 16px; border: 1px solid #f0d9a8; background: #fffdf7; border-radius: 10px; }
.gate h3 { margin-bottom: 8px; }
.advance { margin-top: 14px; padding: 10px 28px; border: none; border-radius: 8px; background: #4285f4; color: #fff; font-size: 1rem; cursor: pointer; }
.advance:disabled { background: #ccc; cursor: not-allowed; }
.final { margin-top: 24px; }
.final h2 { color: #176b3a; }
</style>
