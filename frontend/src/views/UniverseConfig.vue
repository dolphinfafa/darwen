<template>
  <div class="page">
    <h1>新建筛选 · 第 1 步 · 选择股票池</h1>
    <p class="hint">先选股票池，再到下一步配置门槛。</p>

    <div class="presets">
      <div
        v-for="p in presets"
        :key="p.name"
        class="preset-card"
        :class="{ active: selected === p.name }"
        @click="selectPreset(p.name)"
      >
        <h3>{{ p.label }}</h3>
        <div class="muted">{{ p.market }} · {{ p.member_count }} 家</div>
      </div>

      <div class="preset-card" :class="{ active: selected === 'custom' }" @click="selectPreset('custom')">
        <h3>自定义</h3>
        <div class="muted">手工 ticker 列表</div>
      </div>
    </div>

    <div v-if="selected === 'custom'" class="custom-input">
      <label>逗号分隔的 company_id（如 <code>US_0000789019, CN_600519</code>）</label>
      <textarea v-model="customIds" rows="4" placeholder="US_0000789019, CN_600519, US_0000320193"></textarea>
    </div>

    <div class="actions">
      <button :disabled="!canProceed" @click="next">下一步：配置门槛 →</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getUniversePresets } from '../api'

const router = useRouter()
const presets = ref([])
const selected = ref('us_default')
const customIds = ref('')

onMounted(async () => {
  try {
    const { data } = await getUniversePresets()
    presets.value = data
  } catch (e) {
    presets.value = []
  }
})

const canProceed = computed(() => {
  if (selected.value === 'custom') return customIds.value.trim().length > 0
  return !!selected.value
})

function selectPreset(name) { selected.value = name }

function next() {
  const params = { universe: selected.value }
  if (selected.value === 'custom') {
    const ids = customIds.value.split(/[,\s]+/).map(s => s.trim()).filter(Boolean)
    sessionStorage.setItem('darwen_custom_ids', JSON.stringify(ids))
  }
  router.push({ name: 'ScreenConfig', query: params })
}
</script>

<style scoped>
.page { padding: 24px; max-width: 960px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 24px; }
.presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.preset-card {
  padding: 18px; border: 1px solid #e0e0e8; border-radius: 10px;
  cursor: pointer; background: #fff; transition: all .15s;
}
.preset-card:hover { border-color: #4285f4; }
.preset-card.active { border-color: #4285f4; background: #f0f6ff; box-shadow: 0 2px 8px rgba(66,133,244,.15); }
.preset-card h3 { margin: 0 0 6px 0; font-size: 1.05rem; }
.muted { color: #8888a0; font-size: 0.9rem; }
.custom-input { margin-top: 24px; }
.custom-input label { display: block; color: #555; margin-bottom: 6px; }
.custom-input textarea {
  width: 100%; padding: 10px; font-family: ui-monospace, Menlo, monospace;
  font-size: 0.85rem; border: 1px solid #ccc; border-radius: 6px;
}
.actions { margin-top: 32px; text-align: right; }
.actions button {
  padding: 10px 24px; font-size: 1rem; border-radius: 8px;
  background: #4285f4; color: #fff; border: none; cursor: pointer;
}
.actions button:disabled { background: #ccc; cursor: not-allowed; }
</style>
