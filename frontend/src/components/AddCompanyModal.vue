<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <h2>新增股票</h2>
      <p class="muted">输入股票代码，系统会自动拉取财报与指标（异步任务）。</p>

      <div class="field">
        <label>市场</label>
        <div class="radio-group">
          <label class="radio">
            <input type="radio" value="US" v-model="market" />
            美股
          </label>
          <label class="radio">
            <input type="radio" value="CN_A" v-model="market" />
            A 股
          </label>
        </div>
      </div>

      <div class="field">
        <label v-if="market === 'US'">CIK（SEC 公司 ID）</label>
        <label v-else>股票代码（6 位）</label>
        <input
          type="text"
          v-model="code"
          :placeholder="market === 'US' ? '如 320193 (Apple)' : '如 600519 (贵州茅台)'"
          @keyup.enter="submit"
          :disabled="busy"
        />
        <p class="muted small" v-if="market === 'US'">
          在 <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany" target="_blank">SEC EDGAR</a> 输入 ticker 查 CIK
        </p>
      </div>

      <div v-if="task" class="task-status">
        <div class="task-row">任务 #{{ task.task_id }} · {{ statusLabel(task.status) }}</div>
        <div v-if="task.current_stage" class="task-row muted">⚙ {{ stageLabel(task.current_stage) }}</div>
        <div v-if="task.error_msg" class="error">{{ task.error_msg }}</div>
      </div>

      <div class="actions">
        <button class="btn-secondary" @click="emit('close')" :disabled="busy">取消</button>
        <button class="btn-primary" :disabled="!canSubmit || busy" @click="submit">
          {{ busy ? '处理中…' : '开始拉取 →' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { ingestCompany, getIngestStatus } from '../api'

const emit = defineEmits(['close', 'added'])

const market = ref('US')
const code = ref('')
const task = ref(null)
const busy = ref(false)
let poller = null

const canSubmit = computed(() => {
  if (!code.value.trim()) return false
  if (market.value === 'US') return /^\d+$/.test(code.value.trim().replace(/^0+/, '') || '0')
  return /^\d{6}$/.test(code.value.trim())
})

function statusLabel(s) {
  return { pending: '排队中', running: '执行中', completed: '✓ 完成', failed: '✗ 失败' }[s] || s
}
function stageLabel(s) {
  return ({
    queued: '已加入队列',
    fetching_sec_company: '拉取 SEC 公司信息 + XBRL',
    fetching_fiscal_year_end: '获取财年末',
    fetching_tushare_data: '拉取 Tushare 财报数据',
    computing_metrics: '计算指标（ROCE/杠杆/估值等）',
    done: '完成',
    failed: '失败',
  }[s]) || s
}

async function submit() {
  busy.value = true
  try {
    const { data } = await ingestCompany(market.value, code.value.trim())
    task.value = data
    if (data.status === 'completed') {
      emit('added', data.company_id)
    } else {
      poll(data.task_id)
    }
  } catch (e) {
    task.value = {
      task_id: 0, status: 'failed',
      error_msg: e.response?.data?.detail || e.message,
    }
    busy.value = false
  }
}

function poll(taskId) {
  poller = setInterval(async () => {
    try {
      const { data } = await getIngestStatus(taskId)
      task.value = data
      if (data.status === 'completed') {
        clearInterval(poller)
        poller = null
        busy.value = false
        setTimeout(() => emit('added', data.company_id), 800)
      } else if (data.status === 'failed') {
        clearInterval(poller)
        poller = null
        busy.value = false
      }
    } catch (e) {
      // 临时网络错误，继续轮询
    }
  }, 2000)
}

onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<style scoped>
.modal-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: #fff; padding: 24px; border-radius: 10px;
  width: 480px; max-width: 90vw;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}
.modal h2 { margin: 0 0 8px 0; }
.muted { color: #8888a0; font-size: 0.85rem; }
.small { font-size: 0.8rem; margin-top: 4px; }
.field { margin: 14px 0; }
.field label { display: block; font-weight: 600; margin-bottom: 6px; color: #444; }
.field input[type="text"] {
  width: 100%; padding: 8px 12px; border: 1px solid #ccc; border-radius: 6px;
  font-size: 0.95rem; box-sizing: border-box;
}
.radio-group { display: flex; gap: 16px; }
.radio { font-weight: normal; cursor: pointer; }
.radio input { margin-right: 4px; }
.task-status {
  margin: 14px 0; padding: 10px 12px;
  background: #f5f9ff; border-left: 3px solid #4285f4; border-radius: 4px;
}
.task-row { margin: 4px 0; font-size: 0.9rem; }
.error { padding: 8px; background: #fef0f0; color: #c00; border-radius: 4px; margin-top: 8px; font-size: 0.85rem; }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn-primary {
  padding: 8px 18px; border-radius: 6px; background: #4285f4;
  color: #fff; border: none; cursor: pointer; font-size: 0.9rem;
}
.btn-primary:disabled { background: #ccc; cursor: not-allowed; }
.btn-secondary {
  padding: 8px 18px; border-radius: 6px; border: 1px solid #ccc;
  background: #fff; color: #444; cursor: pointer; font-size: 0.9rem;
}
</style>
