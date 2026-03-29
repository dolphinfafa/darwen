<template>
  <div>
    <h2 style="margin-bottom:16px">股票筛选</h2>

    <div class="filters">
      <select v-model="filters.model">
        <option value="v1.0">V1.0 达尔文流程</option>
        <option value="balanced">V0.0 多因子加权</option>
      </select>
      <select v-model="filters.market" @change="onFilterChange">
        <option value="">全部市场</option>
        <option value="US">美股</option>
        <option value="CN_A">A股</option>
      </select>
      <select v-model="filters.industry">
        <option value="">全部行业</option>
        <option v-for="ind in industries" :key="ind" :value="ind">{{ ind }}</option>
      </select>
      <select v-model="filters.tier" @change="onFilterChange">
        <template v-if="isV1">
          <option value="">全部状态</option>
          <option value="BUY">BUY</option>
          <option value="WATCH">WATCH</option>
          <option value="TOO_EXPENSIVE">TOO EXPENSIVE</option>
          <option value="REJECT">REJECT</option>
        </template>
        <template v-else>
          <option value="">全部分层</option>
          <option value="Top">Top</option>
          <option value="Watch">Watch</option>
          <option value="Reject">Reject</option>
        </template>
      </select>
      <button class="btn btn-primary" @click="fetchData">筛选</button>
    </div>

    <div class="card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="rows.length === 0" class="loading">暂无数据</div>
      <template v-else>
        <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary)">
          共 {{ rows.length }} 家
          <span v-if="isV1" style="margin-left:8px">
            BUY {{ tierCount('BUY') }} · WATCH {{ tierCount('WATCH') }} · TOO EXPENSIVE {{ tierCount('TOO_EXPENSIVE') }} · REJECT {{ tierCount('REJECT') }}
          </span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th @click="sortBy('name')">公司</th>
                <th @click="sortBy('market')">市场</th>
                <th>行业</th>
                <th @click="sortBy('total')">{{ isV1 ? '质量分' : '总分' }}</th>
                <th>{{ isV1 ? '状态' : '分层' }}</th>
                <th v-if="isV1" @click="sortBy('survival')">资本回报</th>
                <th v-if="isV1" @click="sortBy('moat')">护城河</th>
                <th v-if="isV1" @click="sortBy('replication')">资本配置</th>
                <th v-if="!isV1" @click="sortBy('survival')">生存力</th>
                <th v-if="!isV1" @click="sortBy('replication')">复制力</th>
                <th v-if="!isV1" @click="sortBy('adaptation')">适应力</th>
                <th v-if="!isV1" @click="sortBy('moat')">优势积累</th>
                <th v-if="!isV1" @click="sortBy('valuation')">估值纪律</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.company_id" @click="goDetail(r.company_id)" style="cursor:pointer">
                <td><strong>{{ r.name }}</strong></td>
                <td>{{ r.market }}</td>
                <td style="font-size:12px;color:var(--text-secondary);white-space:nowrap">{{ r.industry_name || '-' }}</td>
                <td>
                  <div class="score-bar">
                    <div class="bar"><div class="bar-fill" :style="barStyle(r.total)"></div></div>
                    <span class="val">{{ fmt(r.total) }}</span>
                  </div>
                </td>
                <td>
                  <span :class="'tier tier-' + (r.tier || '').replace(' ', '_')">{{ r.tier }}</span>
                </td>
                <td>{{ fmt(r.survival) }}</td>
                <td>{{ fmt(isV1 ? r.moat : r.replication) }}</td>
                <td>{{ fmt(isV1 ? r.replication : r.adaptation) }}</td>
                <td v-if="!isV1">{{ fmt(r.moat) }}</td>
                <td v-if="!isV1">{{ fmt(r.valuation) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getScreener, getIndustries } from '../api'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const industries = ref([])
const filters = ref({ market: '', tier: '', model: 'v1.0', industry: '' })

const isV1 = computed(() => filters.value.model === 'v1.0')
const fmt = (v) => v != null ? v.toFixed(1) : '-'
const tierCount = (t) => rows.value.filter(r => r.tier === t).length

const barStyle = (v) => {
  const pct = Math.min(100, Math.max(0, v || 0))
  const color = pct >= 75 ? '#34a853' : pct >= 55 ? '#fbbc04' : '#ea4335'
  return { width: pct + '%', background: color }
}

const sortBy = (field) => {
  rows.value.sort((a, b) => {
    if (field === 'name') return (a.name || '').localeCompare(b.name || '')
    return (b[field] || 0) - (a[field] || 0)
  })
}

const goDetail = (id) => router.push(`/company/${id}`)

async function loadIndustries() {
  try {
    const { data } = await getIndustries()
    industries.value = data.industries || data || []
  } catch {}
}

function onFilterChange() {
  filters.value.tier = ''
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  try {
    const params = { model: filters.value.model, limit: 500 }
    if (filters.value.market) params.market = filters.value.market
    if (filters.value.tier) params.tier = filters.value.tier
    if (filters.value.industry) params.industry = filters.value.industry
    const { data } = await getScreener(params)
    rows.value = data
  } catch (e) {
    console.error(e)
  }
  loading.value = false
}

watch(() => filters.value.model, () => {
  filters.value.tier = ''
  fetchData()
})

onMounted(() => {
  loadIndustries()
  fetchData()
})
</script>

<style scoped>
.tier-BUY { background: #e6f4ea; color: #137333; }
.tier-WATCH { background: #fef7e0; color: #b06000; }
.tier-TOO_EXPENSIVE { background: #fce8e6; color: #c5221f; }
.tier-REJECT { background: #f1f3f4; color: #5f6368; }
</style>
