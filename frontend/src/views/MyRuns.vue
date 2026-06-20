<template>
  <div class="page">
    <h1>我的筛选历史</h1>
    <p class="hint">所有发起过的筛选任务（按时间倒序）。关闭页面后仍可从这里找回正在运行的任务。</p>

    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!runs.length" class="muted">尚无筛选任务。<router-link to="/universe">新建一个 →</router-link></div>

    <table v-else class="runs">
      <thead>
        <tr>
          <th>Run ID</th>
          <th>股票池</th>
          <th>市场</th>
          <th>as_of</th>
          <th>状态</th>
          <th>进度</th>
          <th>分布</th>
          <th>开始时间</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in runs" :key="r.run_id" @click="openRun(r)">
          <td><code>#{{ r.run_id }}</code></td>
          <td @click.stop>
            <template v-if="editingId === r.run_id">
              <input v-model="editName" class="edit-inp" @keyup.enter="saveRename(r)" @click.stop />
              <button class="link" @click.stop="saveRename(r)">✓</button>
              <button class="link" @click.stop="editingId = null">✕</button>
            </template>
            <template v-else>
              {{ r.universe_name || '-' }}
              <button class="link edit-btn" @click.stop="startEdit(r)" title="重命名">✎</button>
            </template>
          </td>
          <td>{{ r.market }}</td>
          <td>{{ r.as_of_date }}</td>
          <td>
            <span class="status-badge" :class="r.status">{{ statusLabel(r.status) }}</span>
            <span v-if="r.status === 'running' && r.current_company_name" class="current-co">
              ⚙ {{ r.current_company_name }}
            </span>
          </td>
          <td>
            <div class="mini-bar">
              <div class="fill" :style="{ width: progressPct(r) + '%' }"></div>
            </div>
            <span class="muted">{{ r.progress_count }}/{{ r.total_count }}</span>
          </td>
          <td>
            <span class="bucket pass">{{ r.passed_count }}</span> /
            <span class="bucket rej">{{ r.rejected_count }}</span> /
            <span class="bucket rev">{{ r.review_count }}</span>
          </td>
          <td class="muted">{{ formatTime(r.started_at) }}</td>
          <td @click.stop>
            <button class="link" @click="openRun(r)">{{ r.status === 'running' ? '进度 →' : '结果 →' }}</button>
            <button class="link del-btn" @click="removeRun(r)" title="删除此筛选">🗑</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getMyRuns, renameRun, deleteRun } from '../api'

const router = useRouter()
const runs = ref([])
const loading = ref(true)
const error = ref('')
const editingId = ref(null)
const editName = ref('')
let timer = null

async function refresh() {
  try {
    const { data } = await getMyRuns(50)
    runs.value = data
    error.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function statusLabel(s) {
  return { running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }[s] || s
}
function progressPct(r) {
  if (!r.total_count) return 0
  return Math.round(100 * r.progress_count / r.total_count)
}
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}
function openRun(r) {
  router.push({ name: 'FunnelResults', params: { runId: r.run_id } })
}
async function removeRun(r) {
  const label = r.universe_name ? `「${r.universe_name}」` : `#${r.run_id}`
  if (!confirm(`确定删除筛选 ${label} 吗？此操作不可撤销，将一并删除其全部结果。`)) return
  try {
    await deleteRun(r.run_id)
    runs.value = runs.value.filter(x => x.run_id !== r.run_id)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}
function startEdit(r) { editingId.value = r.run_id; editName.value = r.universe_name || '' }
async function saveRename(r) {
  try {
    await renameRun(r.run_id, editName.value.trim() || r.universe_name)
    editingId.value = null
    await refresh()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

onMounted(() => {
  refresh()
  // running 状态的 run 需要轮询刷新
  timer = setInterval(() => {
    if (runs.value.some(r => r.status === 'running')) refresh()
  }, 3000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page { padding: 24px; max-width: 1280px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 16px; font-size: 0.9rem; }
.muted { color: #8888a0; font-size: 0.85rem; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }
.runs { width: 100%; border-collapse: collapse; background: #fff; font-size: 0.9rem; }
.runs th, .runs td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f5; }
.runs th { background: #fafafd; color: #555; font-weight: 600; font-size: 0.85rem; }
.runs tbody tr:hover { background: #f5f9ff; cursor: pointer; }
.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 10px;
  font-size: 0.75rem; font-weight: 600;
}
.status-badge.running { background: #fff4d6; color: #b06000; }
.status-badge.completed { background: #d6f5e0; color: #176b3a; }
.status-badge.failed { background: #fde0e0; color: #c00; }
.status-badge.cancelled { background: #e8e8ec; color: #666; }
.current-co {
  display: block; margin-top: 4px; font-size: 0.78rem; color: #4285f4;
}
.mini-bar {
  width: 80px; height: 6px; background: #f0f0f5;
  border-radius: 3px; overflow: hidden; display: inline-block; vertical-align: middle;
  margin-right: 8px;
}
.mini-bar .fill { height: 100%; background: #4285f4; transition: width 0.3s; }
.bucket {
  display: inline-block; padding: 1px 7px; border-radius: 8px;
  font-size: 0.78rem; font-weight: 600;
}
.bucket.pass { background: #d6f5e0; color: #176b3a; }
.bucket.rej { background: #fde0e0; color: #c00; }
.bucket.rev { background: #ffe4cc; color: #b04000; }
.link {
  background: none; border: none; color: #4285f4;
  cursor: pointer; padding: 0 4px; font-size: 0.85rem;
}
.edit-btn { opacity: 0.4; }
.runs tbody tr:hover .edit-btn { opacity: 1; }
.del-btn { color: #c0392b; opacity: 0.4; }
.runs tbody tr:hover .del-btn { opacity: 1; }
.del-btn:hover { color: #e74c3c; }
.edit-inp { padding: 3px 8px; border: 1px solid #4285f4; border-radius: 5px; font-size: 0.85rem; width: 140px; }
</style>
