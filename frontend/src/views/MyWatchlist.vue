<template>
  <div class="page">
    <h1>我的股票池</h1>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="layout">
      <!-- 左：池列表 -->
      <aside class="side">
        <div class="new">
          <input v-model="newName" placeholder="新建股票池名称" @keyup.enter="doCreate" />
          <button class="btn" :disabled="!newName.trim()" @click="doCreate">＋</button>
        </div>
        <ul class="wl-list">
          <li v-for="w in lists" :key="w.id" :class="{ active: w.id === activeId }" @click="select(w.id)">
            <span class="nm">{{ w.name }}</span>
            <span class="cnt">{{ w.item_count }}</span>
          </li>
        </ul>
        <div v-if="!lists.length" class="muted">还没有股票池。在右侧或股票详情页"进入我的股票池"创建。</div>
      </aside>

      <!-- 右：选中池详情 -->
      <section class="main" v-if="detail">
        <div class="main-hd">
          <template v-if="editing">
            <input v-model="editName" @keyup.enter="doRename" class="rename-input" />
            <button class="btn" @click="doRename">保存</button>
            <button class="btn ghost" @click="editing = false">取消</button>
          </template>
          <template v-else>
            <h2>{{ detail.name }} <span class="muted">（{{ detail.items.length }} 只）</span></h2>
            <button class="btn ghost" @click="startRename">✎ 改名</button>
            <button class="btn danger" @click="doDelete">删除池</button>
          </template>
        </div>

        <table v-if="detail.items.length" class="items">
          <thead>
            <tr><th>Ticker</th><th>公司</th><th>市场</th><th>行业</th><th>备注</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="it in detail.items" :key="it.company_id">
              <td><code>{{ it.ticker || '-' }}</code></td>
              <td>{{ it.name }}</td>
              <td><span class="market" :class="it.market.toLowerCase()">{{ it.market }}</span></td>
              <td>{{ it.industry_name || '-' }}</td>
              <td class="note">{{ it.note || '-' }}</td>
              <td class="op">
                <button v-if="it.source_run_id" class="link" @click="goDetail(it)">详情</button>
                <button class="link danger" @click="doRemove(it.company_id)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="muted">该池为空。</div>
      </section>
      <section class="main muted" v-else>← 选择或新建一个股票池</section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  getWatchlists, createWatchlist, renameWatchlist, deleteWatchlist,
  getWatchlistDetail, removeWatchlistItem,
} from '../api'

const router = useRouter()
const lists = ref([])
const activeId = ref(null)
const detail = ref(null)
const newName = ref('')
const editing = ref(false)
const editName = ref('')
const error = ref('')

async function loadLists() {
  try {
    const { data } = await getWatchlists()
    lists.value = data
    if (!activeId.value && data.length) select(data[0].id)
    else if (activeId.value) await loadDetail()
  } catch (e) { error.value = e.response?.data?.detail || e.message }
}
async function loadDetail() {
  if (!activeId.value) { detail.value = null; return }
  try {
    const { data } = await getWatchlistDetail(activeId.value)
    detail.value = data
  } catch (e) { error.value = e.response?.data?.detail || e.message }
}
function select(id) { activeId.value = id; editing.value = false; loadDetail() }

async function doCreate() {
  if (!newName.value.trim()) return
  try {
    const { data } = await createWatchlist(newName.value.trim())
    newName.value = ''
    await loadLists()
    select(data.id)
  } catch (e) { error.value = e.response?.data?.detail || e.message }
}
function startRename() { editName.value = detail.value.name; editing.value = true }
async function doRename() {
  try {
    await renameWatchlist(activeId.value, editName.value.trim())
    editing.value = false
    await loadLists()
  } catch (e) { error.value = e.response?.data?.detail || e.message }
}
async function doDelete() {
  if (!confirm(`确定删除股票池"${detail.value.name}"？`)) return
  try {
    await deleteWatchlist(activeId.value)
    activeId.value = null; detail.value = null
    await loadLists()
  } catch (e) { error.value = e.response?.data?.detail || e.message }
}
async function doRemove(cid) {
  try { await removeWatchlistItem(activeId.value, cid); await loadDetail(); await loadLists() }
  catch (e) { error.value = e.response?.data?.detail || e.message }
}
function goDetail(it) {
  router.push({ name: 'CompanyDetailV2', params: { runId: it.source_run_id, companyId: it.company_id } })
}

onMounted(loadLists)
</script>

<style scoped>
.page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; margin-bottom: 12px; }
.layout { display: flex; gap: 20px; margin-top: 16px; }
.side { width: 260px; flex-shrink: 0; }
.new { display: flex; gap: 6px; margin-bottom: 12px; }
.new input { flex: 1; padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; }
.wl-list { list-style: none; padding: 0; margin: 0; }
.wl-list li { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border: 1px solid #e0e0e8; border-radius: 8px; margin-bottom: 6px; cursor: pointer; }
.wl-list li:hover { background: #f5f9ff; }
.wl-list li.active { border-color: #4285f4; background: #f0f6ff; }
.wl-list .cnt { font-size: 0.8rem; background: #f0f0f5; color: #666; padding: 1px 8px; border-radius: 10px; }
.main { flex: 1; }
.main-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.main-hd h2 { margin: 0; }
.rename-input { padding: 6px 10px; border: 1px solid #4285f4; border-radius: 6px; font-size: 1rem; }
.btn { padding: 6px 14px; border: 1px solid #4285f4; background: #4285f4; color: #fff; border-radius: 6px; cursor: pointer; }
.btn.ghost { background: #fff; color: #4285f4; }
.btn.danger { background: #fff; color: #c00; border-color: #f0caca; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.items { width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }
.items th, .items td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #f0f0f5; }
.items th { background: #fafafd; color: #555; font-weight: 600; font-size: 0.85rem; }
.items code { background: #f0f0f5; padding: 1px 6px; border-radius: 3px; }
.market { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.market.us { background: #d6e7f5; color: #1768b0; }
.market.cn_a { background: #fde0e0; color: #c00; }
.note { color: #888; max-width: 200px; }
.op { white-space: nowrap; text-align: right; }
.link { background: none; border: none; color: #4285f4; cursor: pointer; padding: 0 6px; font-size: 0.85rem; }
.link.danger { color: #c00; }
.muted { color: #8888a0; }
</style>
