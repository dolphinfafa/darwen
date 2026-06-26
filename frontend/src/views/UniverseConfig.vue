<template>
  <div class="page">
    <h1>新建筛选 · 选择股票池</h1>
    <p class="hint">从下表勾选公司进入股票池，或点"新增股票"输入 CIK/代码自动拉取。</p>

    <div class="toolbar">
      <select v-model="filters.market" @change="reload">
        <option value="">全部市场</option>
        <option value="US">美股</option>
        <option value="CN_A">A 股</option>
      </select>

      <select v-model="filters.industry" @change="reload">
        <option value="">全部行业</option>
        <option v-for="ind in industries" :key="ind.industry_name" :value="ind.industry_name">
          {{ ind.industry_name }} ({{ ind.count }})
        </option>
      </select>

      <input
        type="text"
        v-model="filters.search"
        placeholder="搜索 ticker / 公司名 / 代码"
        @keyup.enter="reload"
      />
      <button class="btn-secondary" @click="reload">🔍 搜索</button>

      <span class="spacer"></span>

      <button class="btn-secondary" @click="showAddModal = true">➕ 新增股票</button>
      <button class="btn-secondary" @click="selectAll" :disabled="!rows.length">全选当前</button>
      <button class="btn-secondary" @click="clearSelection" :disabled="!selected.size">清空</button>
    </div>

    <div class="status-bar">
      <span class="muted">显示 {{ rows.length }} 家</span>
      ·
      <strong>已选 {{ selected.size }} 家</strong>
    </div>

    <div v-if="loading" class="muted center">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <table v-else-if="rows.length" class="companies">
      <thead>
        <tr>
          <th width="40">
            <input type="checkbox" :checked="allCurrentSelected" @change="togglePage" />
          </th>
          <th>Ticker</th>
          <th>公司</th>
          <th>市场</th>
          <th>行业</th>
          <th>类型</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.company_id"
            :class="{ selected: selected.has(r.company_id) }"
            @click="toggle(r.company_id)">
          <td>
            <input type="checkbox"
                   :checked="selected.has(r.company_id)"
                   @click.stop="toggle(r.company_id)" />
          </td>
          <td><code>{{ r.ticker || '-' }}</code></td>
          <td>{{ r.name }}</td>
          <td>
            <span class="market" :class="r.market.toLowerCase()">{{ r.market }}</span>
          </td>
          <td>{{ r.industry_name || '-' }}</td>
          <td><span class="instrument">{{ r.instrument_type }}</span></td>
        </tr>
      </tbody>
    </table>
    <div v-else class="muted center">无匹配公司</div>

    <fieldset class="roce-config">
      <legend>ROCE 门槛（漏斗第一层）</legend>
      <label>
        最低 ROCE 阈值
        <input type="number" step="0.01" min="0" max="1" v-model.number="roce.threshold" />
        <span class="muted">≈ {{ (roce.threshold * 100).toFixed(0) }}%（默认 20%）</span>
      </label>
      <label>
        回溯年数
        <select v-model.number="roce.lookback_years">
          <option :value="3">近 3 年</option>
          <option :value="5">近 5 年</option>
          <option :value="7">近 7 年</option>
          <option :value="10">近 10 年</option>
        </select>
        <span class="muted">计算当前往前 N 年的 ROCE 中位数</span>
      </label>
      <label>
        AI 介入
        <select v-model="aiMode">
          <option value="off">不启用（纯规则，最快）</option>
          <option value="key_stage">仅关键阶段（风险层 AI）</option>
          <option value="full">全程（稳健层 + 风险层 AI）</option>
        </select>
        <span class="muted">AI 需先在账户设置绑定 key</span>
      </label>
    </fieldset>

    <div class="actions">
      <button class="btn-primary" :disabled="!selected.size || launching" @click="start">
        {{ launching ? '启动中…' : `开始筛选 →（${selected.size} 家）` }}
      </button>
    </div>

    <!-- 新增股票模态框 -->
    <AddCompanyModal
      v-if="showAddModal"
      @close="showAddModal = false"
      @added="onCompanyAdded"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { getCompanies, getIndustries, createScreenRun } from '../api'
import AddCompanyModal from '../components/AddCompanyModal.vue'

const router = useRouter()
const rows = ref([])
const industries = ref([])
const loading = ref(false)
const error = ref('')
const showAddModal = ref(false)
const selected = ref(new Set())  // 选中的 company_id
const launching = ref(false)

const filters = reactive({
  market: 'US',  // 默认美股
  industry: '',
  search: '',
})

// ROCE 门槛配置（漏斗第一层，内嵌于本页，取代独立的"配置门槛"步骤）
const roce = reactive({
  threshold: 0.20,
  lookback_years: 5,
})
// AI 介入范围：off=纯规则 | key_stage=仅风险层 | full=稳健+风险层全程
const aiMode = ref('off')

// 从 sessionStorage 恢复选中（刷新/返回后保留股票池选择）
const STORAGE_KEY = 'darwen_universe_selected'

function loadSelection() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) selected.value = new Set(JSON.parse(raw))
  } catch {}
}
function saveSelection() {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...selected.value]))
}

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const params = {}
    if (filters.market) params.market = filters.market
    if (filters.industry) params.industry = filters.industry
    if (filters.search) params.search = filters.search
    params.limit = 5000   // 覆盖全市场（美股 548 + A股 1800+），避免被默认值截断
    const { data } = await getCompanies(params)
    rows.value = data
    // 切市场时也刷新行业列表
    const { data: inds } = await getIndustries(filters.market)
    industries.value = inds
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function toggle(cid) {
  const s = selected.value
  if (s.has(cid)) s.delete(cid)
  else s.add(cid)
  selected.value = new Set(s)
  saveSelection()
}

const allCurrentSelected = computed(() => {
  return rows.value.length > 0 && rows.value.every(r => selected.value.has(r.company_id))
})

function togglePage(e) {
  if (e.target.checked) {
    rows.value.forEach(r => selected.value.add(r.company_id))
  } else {
    rows.value.forEach(r => selected.value.delete(r.company_id))
  }
  selected.value = new Set(selected.value)
  saveSelection()
}

function selectAll() {
  rows.value.forEach(r => selected.value.add(r.company_id))
  selected.value = new Set(selected.value)
  saveSelection()
}

function clearSelection() {
  selected.value = new Set()
  saveSelection()
}

function onCompanyAdded(companyId) {
  // ingest 完成后，加入选中 + 刷新列表
  selected.value.add(companyId)
  selected.value = new Set(selected.value)
  saveSelection()
  showAddModal.value = false
  reload()
}

async function start() {
  if (!selected.value.size || launching.value) return
  launching.value = true
  error.value = ''
  try {
    const { data } = await createScreenRun({
      universe_name: '自定义筛选',
      company_ids: [...selected.value],
      roce_threshold: roce.threshold,
      roce_lookback_years: roce.lookback_years,
      ai_mode: aiMode.value,
      // 全自动三层漏斗：ROCE→稳健性→风险性逐层自动推进，最终通过风险层的即入选列表
      auto_advance: true,
    })
    router.push({ name: 'FunnelResults', params: { runId: data.run_id } })
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
    launching.value = false
  }
}

onMounted(() => {
  loadSelection()
  reload()
})
</script>

<style scoped>
.page { padding: 24px; max-width: 1280px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 16px; }
.toolbar {
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  margin-bottom: 12px;
}
.toolbar select, .toolbar input[type="text"] {
  padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.9rem;
}
.toolbar input[type="text"] { flex: 1; min-width: 200px; max-width: 300px; }
.toolbar .spacer { flex: 1; }
.btn-secondary {
  padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px;
  background: #fff; color: #444; cursor: pointer; font-size: 0.9rem;
}
.btn-secondary:hover:not(:disabled) { border-color: #4285f4; color: #4285f4; }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary {
  padding: 10px 24px; border-radius: 8px; background: #4285f4;
  color: #fff; border: none; cursor: pointer; font-size: 1rem;
}
.btn-primary:disabled { background: #ccc; cursor: not-allowed; }
.status-bar { font-size: 0.9rem; margin-bottom: 8px; color: #555; }
.muted { color: #8888a0; }
.center { text-align: center; padding: 30px; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }

.companies { width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }
.companies th, .companies td {
  padding: 8px 12px; text-align: left; border-bottom: 1px solid #f0f0f5;
}
.companies th {
  background: #fafafd; color: #555; font-weight: 600; font-size: 0.85rem;
  position: sticky; top: 0;
}
.companies tbody tr { cursor: pointer; }
.companies tbody tr:hover { background: #f5f9ff; }
.companies tbody tr.selected { background: #f0f6ff; }
.companies code { background: #f0f0f5; padding: 1px 6px; border-radius: 3px; font-size: 0.85em; }

.market {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 0.75rem; font-weight: 600;
}
.market.us { background: #d6e7f5; color: #1768b0; }
.market.cn_a { background: #fde0e0; color: #c00; }
.instrument {
  font-size: 0.75rem; color: #888;
}
.actions { margin-top: 16px; text-align: right; }

.roce-config {
  margin-top: 24px; border: 1px solid #e0e0e8; border-radius: 10px;
  padding: 14px 18px; display: flex; gap: 32px; flex-wrap: wrap; align-items: center;
}
.roce-config legend { font-weight: 600; color: #444; padding: 0 6px; }
.roce-config label { display: flex; align-items: center; gap: 8px; font-size: 0.9rem; color: #444; }
.roce-config input[type="number"] { width: 80px; padding: 5px 8px; border: 1px solid #ccc; border-radius: 6px; }
.roce-config select { padding: 5px 8px; border: 1px solid #ccc; border-radius: 6px; }
</style>
