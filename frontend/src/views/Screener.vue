<template>
  <div>
    <h2 style="margin-bottom:16px">股票筛选</h2>

    <div class="filters">
      <select v-model="filters.market" @change="onMarketChange">
        <option value="">全部市场</option>
        <option value="US">美股</option>
        <option value="CN_A">A股</option>
      </select>
      <select v-model="filters.industry">
        <option value="">全部行业</option>
        <option v-for="ind in industries" :key="ind" :value="ind">{{ ind }}</option>
      </select>
      <select v-model="filters.tier">
        <option value="">全部分层</option>
        <option value="Top">Top</option>
        <option value="Watch">Watch</option>
        <option value="Reject">Reject</option>
      </select>
      <select v-model="filters.model">
        <option value="balanced">基准</option>
        <option value="conservative">保守</option>
        <option value="aggressive">激进</option>
      </select>
      <button class="btn btn-primary" @click="fetchData">筛选</button>
    </div>

    <div class="card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="rows.length === 0" class="loading">暂无数据</div>
      <template v-else>
        <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary)">
          共 {{ rows.length }} 家
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th @click="sortBy('name')">公司</th>
                <th @click="sortBy('market')">市场</th>
                <th>行业</th>
                <th @click="sortBy('total')">总分</th>
                <th>分层</th>
                <th @click="sortBy('survival')">生存力</th>
                <th @click="sortBy('replication')">复制力</th>
                <th @click="sortBy('adaptation')">适应力</th>
                <th @click="sortBy('moat')">优势积累</th>
                <th @click="sortBy('valuation')">估值纪律</th>
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
                <td><span :class="'tier tier-' + r.tier">{{ r.tier }}</span></td>
                <td>{{ fmt(r.survival) }}</td>
                <td>{{ fmt(r.replication) }}</td>
                <td>{{ fmt(r.adaptation) }}</td>
                <td>{{ fmt(r.moat) }}</td>
                <td>{{ fmt(r.valuation) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScreener, getIndustries } from '../api'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const industries = ref([])
const filters = ref({ market: '', tier: '', model: 'balanced', industry: '' })

const fmt = (v) => v != null ? v.toFixed(1) : '-'

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

function onMarketChange() {
  filters.value.industry = ''
  loadIndustries()
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

onMounted(() => {
  loadIndustries()
  fetchData()
})
</script>
