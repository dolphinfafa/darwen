<template>
  <div class="page">
    <h1>新建筛选 · 第 2 步 · 配置门槛</h1>
    <p class="hint">股票池：<strong>{{ universeLabel }}</strong></p>

    <form class="config-form" @submit.prevent="launch">
      <fieldset>
        <legend>质量门槛（Q-Layer）</legend>
        <label>
          ROCE 阈值
          <input type="number" step="0.01" min="0" max="1" v-model.number="form.roce_threshold" />
          <span class="muted">默认 0.20（书中标准）</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>风控敏感度（R-Layer）</legend>
        <label class="radio">
          <input type="radio" value="strict" v-model="form.risk_sensitivity" />
          严格 <span class="muted">net_debt/EBIT ≤ 3，利息保障 ≥ 4</span>
        </label>
        <label class="radio">
          <input type="radio" value="standard" v-model="form.risk_sensitivity" />
          标准 <span class="muted">net_debt/EBIT ≤ 4，利息保障 ≥ 3</span>
        </label>
        <label class="radio">
          <input type="radio" value="loose" v-model="form.risk_sensitivity" />
          宽松 <span class="muted">net_debt/EBIT ≤ 6，利息保障 ≥ 2</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>估值模式（V-Layer）</legend>
        <label class="radio">
          <input type="radio" value="strict" v-model="form.valuation_mode" />
          严格 <span class="muted">PE ≤ 14.9 才视为 Cheap</span>
        </label>
        <label class="radio">
          <input type="radio" value="standard" v-model="form.valuation_mode" />
          标准 <span class="muted">分级 14.9 / 18 / 22 视等级</span>
        </label>
        <label class="radio">
          <input type="radio" value="loose" v-model="form.valuation_mode" />
          宽松
        </label>
      </fieldset>

      <fieldset>
        <legend>AI 风险层（M4）</legend>
        <label>
          <input type="checkbox" v-model="form.enable_ai_risk_layer" />
          启用 AI 风险层（需账户已绑定 key）
        </label>
        <label v-if="form.enable_ai_risk_layer">
          AI Provider
          <select v-model="form.ai_provider">
            <option :value="null">使用账户默认</option>
            <option value="chatgpt">ChatGPT 5</option>
            <option value="minimax">MiniMax 2.7</option>
          </select>
        </label>
      </fieldset>

      <fieldset>
        <legend>点时日期</legend>
        <label>
          as_of_date <input type="date" v-model="form.as_of_date" />
          <span class="muted">回测点时基准</span>
        </label>
      </fieldset>

      <div class="actions">
        <button type="button" @click="goBack">← 上一步</button>
        <button type="submit" :disabled="loading">{{ loading ? '启动中…' : '启动筛选 →' }}</button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
    </form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createScreenRun } from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')

const universe = route.query.universe || 'us_default'
const universeLabel = computed(() => ({
  us_default: '美股全量池',
  cn_default: 'A 股蓝筹池',
  all: '混合全量',
  custom: '自定义池',
}[universe] || universe))

const form = reactive({
  roce_threshold: 0.20,
  risk_sensitivity: 'standard',
  valuation_mode: 'strict',
  enable_ai_risk_layer: false,
  ai_provider: null,
  as_of_date: '2024-12-31',
})

function goBack() { router.push({ name: 'UniverseConfig' }) }

async function launch() {
  loading.value = true
  error.value = ''
  try {
    const body = {
      universe_name: universe,
      ...form,
    }
    if (universe === 'custom') {
      body.company_ids = JSON.parse(sessionStorage.getItem('darwen_custom_ids') || '[]')
      if (!body.company_ids.length) throw new Error('自定义股票池为空')
    } else {
      body.preset = universe
    }
    const { data } = await createScreenRun(body)
    router.push({ name: 'ScreenRun', params: { runId: data.run_id } })
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '启动失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page { padding: 24px; max-width: 720px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 16px; }
.config-form { display: flex; flex-direction: column; gap: 18px; }
fieldset {
  border: 1px solid #e0e0e8; border-radius: 8px; padding: 14px 18px;
}
legend { padding: 0 8px; font-weight: 600; color: #555; }
fieldset label { display: block; margin: 8px 0; }
.radio { font-weight: normal; }
.muted { color: #8888a0; font-size: 0.85rem; margin-left: 6px; }
input[type="number"], input[type="date"], select {
  margin-left: 8px; padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px;
}
.actions { display: flex; justify-content: space-between; margin-top: 16px; }
.actions button {
  padding: 10px 20px; font-size: 1rem; border-radius: 8px; cursor: pointer;
  border: 1px solid #ccc; background: #fff;
}
.actions button[type="submit"] { background: #4285f4; color: #fff; border-color: #4285f4; }
.actions button:disabled { background: #ccc; cursor: not-allowed; }
.error { padding: 10px; background: #fef0f0; color: #c00; border-radius: 6px; }
</style>
