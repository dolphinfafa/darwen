<template>
  <div class="page">
    <h1>筛选执行中…</h1>
    <div v-if="run" class="card">
      <p>Run ID: <code>{{ run.run_id }}</code></p>
      <p>股票池：{{ run.universe_name }} · {{ run.market }} · 共 {{ run.total_count }} 家</p>
      <p>状态：<span :class="['status-badge', run.status]">{{ run.status }}</span></p>

      <div class="progress">
        <div class="bar">
          <div class="fill" :style="{ width: progressPct + '%' }"></div>
        </div>
        <div class="muted">{{ completed }}/{{ run.total_count }} 已处理 · 通过 {{ run.passed_count }} · 排除 {{ run.rejected_count }} · 覆核 {{ run.review_count }}</div>
      </div>

      <div v-if="run.status === 'completed'" class="actions">
        <button @click="goResults">查看结果 →</button>
      </div>
      <div v-if="run.status === 'failed'" class="error">
        失败：{{ run.error_msg }}
      </div>
    </div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>加载中…</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScreenRunStatus } from '../api'

const route = useRoute()
const router = useRouter()
const runId = Number(route.params.runId)
const run = ref(null)
const error = ref('')
let timer = null

const completed = computed(() => {
  if (!run.value) return 0
  return (run.value.passed_count || 0) + (run.value.rejected_count || 0) + (run.value.review_count || 0)
})
const progressPct = computed(() => {
  if (!run.value?.total_count) return 0
  return Math.min(100, Math.round(100 * completed.value / run.value.total_count))
})

async function refresh() {
  try {
    const { data } = await getScreenRunStatus(runId)
    run.value = data
    if (data.status === 'completed' || data.status === 'failed') {
      clearInterval(timer)
      timer = null
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
    clearInterval(timer)
  }
}

function goResults() {
  router.push({ name: 'ScreenResults', params: { runId } })
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 1500)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page { padding: 24px; max-width: 720px; margin: 0 auto; }
.card {
  padding: 20px; border: 1px solid #e0e0e8; border-radius: 10px; background: #fff;
  display: flex; flex-direction: column; gap: 12px;
}
.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 0.85rem; font-weight: 600;
}
.status-badge.running { background: #fff4d6; color: #b06000; }
.status-badge.completed { background: #d6f5e0; color: #176b3a; }
.status-badge.failed { background: #fde0e0; color: #c00; }
.progress { margin-top: 8px; }
.bar { width: 100%; height: 10px; background: #f0f0f5; border-radius: 6px; overflow: hidden; }
.fill { height: 100%; background: #4285f4; transition: width .3s; }
.muted { color: #8888a0; font-size: 0.85rem; margin-top: 6px; }
.actions { margin-top: 8px; text-align: right; }
.actions button {
  padding: 10px 24px; font-size: 1rem; border-radius: 8px;
  background: #34a853; color: #fff; border: none; cursor: pointer;
}
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }
</style>
