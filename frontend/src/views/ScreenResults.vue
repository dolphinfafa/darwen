<template>
  <div class="page">
    <h1>筛选结果 · Run #{{ runId }}</h1>

    <div class="bucket-tabs">
      <button
        v-for="b in buckets"
        :key="b"
        :class="{ active: activeBucket === b }"
        @click="activeBucket = b"
      >
        {{ bucketLabel(b) }}
        <span class="badge" :class="bucketClass(b)">{{ counts[b] || 0 }}</span>
      </button>
    </div>

    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <table v-else-if="rows[activeBucket]?.length" class="results">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>公司</th>
          <th>市场</th>
          <th>行业</th>
          <th>ROCE 5Y</th>
          <th>PE_TTM</th>
          <th>原因码</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows[activeBucket]" :key="r.company_id" @click="goDetail(r.company_id)">
          <td><code>{{ r.ticker || '-' }}</code></td>
          <td>{{ r.name }}</td>
          <td>{{ r.market }}</td>
          <td>{{ r.industry_name || '-' }}</td>
          <td>{{ fmtPct(r.metrics_snapshot?.roce_5y_median) }}</td>
          <td>{{ fmtNum(r.metrics_snapshot?.pe_ttm) }}</td>
          <td class="codes">
            <span v-for="c in r.reason_codes" :key="c" class="code-pill">{{ c }}</span>
          </td>
          <td><button class="link">详情 →</button></td>
        </tr>
      </tbody>
    </table>
    <div v-else class="muted">此分桶为空</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScreenRunResults } from '../api'

const route = useRoute()
const router = useRouter()
const runId = Number(route.params.runId)
const buckets = ['HighConviction', 'NearFairPrice', 'TooExpensive', 'Review', 'Rejected']
const activeBucket = ref('HighConviction')
const counts = ref({})
const rows = ref({})
const loading = ref(true)
const error = ref('')

function bucketLabel(b) {
  return ({
    HighConviction: '高确信',
    NearFairPrice: '接近合理价',
    TooExpensive: '太贵',
    Review: '人工覆核',
    Rejected: '排除',
  }[b]) + ` (${counts.value[b] || 0})`
}

function bucketClass(b) {
  return ({
    HighConviction: 'green',
    NearFairPrice: 'blue',
    TooExpensive: 'yellow',
    Review: 'orange',
    Rejected: 'red',
  }[b])
}

function fmtPct(v) {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}
function fmtNum(v) {
  if (v == null) return '-'
  return Number(v).toFixed(1) + 'x'
}

function goDetail(cid) {
  router.push({ name: 'CompanyDetailV2', params: { runId, companyId: cid } })
}

onMounted(async () => {
  try {
    const { data } = await getScreenRunResults(runId, 100)
    counts.value = data.counts || {}
    rows.value = data.rows || {}
    // 默认切到第一个非空桶
    const first = buckets.find(b => (counts.value[b] || 0) > 0)
    if (first) activeBucket.value = first
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 24px; max-width: 1280px; margin: 0 auto; }
.bucket-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.bucket-tabs button {
  padding: 8px 14px; border: 1px solid #e0e0e8; border-radius: 8px;
  background: #fff; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 6px;
}
.bucket-tabs button.active { border-color: #4285f4; background: #f0f6ff; }
.badge { font-size: 0.75rem; padding: 1px 6px; border-radius: 8px; }
.badge.green { background: #d6f5e0; color: #176b3a; }
.badge.blue { background: #d6e7f5; color: #1768b0; }
.badge.yellow { background: #fff4d6; color: #b06000; }
.badge.orange { background: #ffe4cc; color: #b04000; }
.badge.red { background: #fde0e0; color: #c00; }
.results { width: 100%; border-collapse: collapse; background: #fff; }
.results th, .results td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #f0f0f5; font-size: 0.9rem; }
.results th { background: #fafafd; color: #555; font-weight: 600; }
.results tbody tr:hover { background: #f5f9ff; cursor: pointer; }
.codes { max-width: 320px; }
.code-pill {
  display: inline-block; padding: 1px 6px; margin: 2px;
  background: #f0f0f5; border-radius: 4px; font-size: 0.75rem;
  color: #555;
}
.link {
  background: none; border: none; color: #4285f4; cursor: pointer; padding: 0;
}
.muted { color: #8888a0; padding: 20px; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }
</style>
