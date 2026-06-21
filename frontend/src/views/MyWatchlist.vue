<template>
  <div class="page">
    <div class="hd">
      <h1>我的股票池</h1>
      <button class="btn ghost" :disabled="loading" @click="reload">⟳ 刷新行情</button>
    </div>
    <p class="hint">收藏的股票（含最新收盘价与市盈率）。在筛选结果或股票详情页点「进入我的股票池」加入。</p>
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="!stocks.length" class="muted">
      还没有收藏股票。去<router-link to="/universe">新建筛选</router-link>，在结果或详情页加入。
    </div>

    <table v-else class="items">
      <thead>
        <tr>
          <th>Ticker</th><th>公司</th><th>市场</th>
          <th class="num">最新价</th>
          <th class="num">市盈率<span class="dtip" data-tip="PE(TTM) = 市值 ÷ 滚动 12 个月净利润（YTD 差分：最近完整财年 + 本年最新YTD − 去年同期YTD）。负盈利显示 —。">ⓘ</span></th>
          <th>行业</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in stocks" :key="s.company_id">
          <td><code>{{ s.ticker || '-' }}</code></td>
          <td class="nm">{{ s.name }}</td>
          <td><span class="market" :class="s.market.toLowerCase()">{{ s.market }}</span></td>
          <td class="num">
            {{ fmtPrice(s.latest_close) }}
            <span v-if="s.latest_trade_date" class="asof">{{ s.latest_trade_date }}</span>
          </td>
          <td class="num pe">{{ fmtPe(s.pe_ttm) }}</td>
          <td>{{ s.industry_name || '-' }}</td>
          <td class="op">
            <button v-if="s.source_run_id" class="link" @click="goDetail(s)">详情</button>
            <button class="link danger" @click="doRemove(s)">移除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getMyStocks, removeMyStock } from '../api'

const router = useRouter()
const stocks = ref([])
const loading = ref(true)
const error = ref('')

async function reload() {
  loading.value = true
  try {
    const { data } = await getMyStocks()
    stocks.value = data
    error.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function fmtPrice(v) { return v == null ? '-' : v.toFixed(2) }
function fmtPe(v) { return v == null ? '—' : v.toFixed(1) + 'x' }

function goDetail(s) {
  router.push({ name: 'CompanyDetailV2', params: { runId: s.source_run_id, companyId: s.company_id } })
}
async function doRemove(s) {
  if (!confirm(`从我的股票池移除 ${s.name}？`)) return
  try {
    await removeMyStock(s.company_id)
    stocks.value = stocks.value.filter(x => x.company_id !== s.company_id)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

onMounted(reload)
</script>

<style scoped>
.page { padding: 24px; max-width: 1100px; margin: 0 auto; }
.hd { display: flex; align-items: center; justify-content: space-between; }
.hd h1 { margin: 0; }
.hint { color: #8888a0; font-size: 0.9rem; margin: 6px 0 16px; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; margin-bottom: 12px; }
.muted { color: #8888a0; }
.btn { padding: 6px 14px; border: 1px solid #4285f4; background: #fff; color: #4285f4; border-radius: 6px; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.items { width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }
.items th, .items td { padding: 9px 12px; text-align: left; border-bottom: 1px solid #f0f0f5; }
.items th { background: #fafafd; color: #555; font-weight: 600; font-size: 0.85rem; }
.items th.num, .items td.num { text-align: right; }
.items code { background: #f0f0f5; padding: 1px 6px; border-radius: 3px; }
.nm { font-weight: 500; }
.num { font-variant-numeric: tabular-nums; }
.pe { font-weight: 600; color: #1a3a8a; }
.asof { display: block; font-size: 0.72rem; color: #aaa; }
.market { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.market.us { background: #d6e7f5; color: #1768b0; }
.market.cn_a { background: #fde0e0; color: #c00; }
.op { white-space: nowrap; text-align: right; }
.link { background: none; border: none; color: #4285f4; cursor: pointer; padding: 0 6px; font-size: 0.85rem; }
.link.danger { color: #c00; }
</style>
