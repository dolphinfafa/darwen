<template>
  <div>
    <div style="margin-bottom:16px">
      <router-link to="/" class="btn">&larr; 返回筛选</router-link>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="!detail" class="loading">未找到数据</div>
    <template v-else>
      <div class="card" style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
          <div>
            <h2 style="margin:0">{{ detail.company.name }}</h2>
            <span style="color:var(--text-secondary)">
              {{ detail.company.ticker }} · {{ detail.company.market }} · {{ detail.company.industry_name || '未分类' }}
            </span>
          </div>
          <div style="text-align:right">
            <div style="font-size:32px;font-weight:700">{{ fmt(detail.score.total) }}</div>
            <span :class="'tier tier-' + detail.score.tier" style="font-size:14px">{{ detail.score.tier }}</span>
            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px">
              {{ detail.score.model_version }} · {{ detail.score.asof_date }}
            </div>
          </div>
        </div>
      </div>

      <div class="detail-grid">
        <div class="card">
          <h3 style="margin-bottom:12px">五维雷达图</h3>
          <div class="radar-container">
            <v-chart :option="radarOption" autoresize />
          </div>
        </div>

        <div class="card">
          <h3 style="margin-bottom:12px">维度得分</h3>
          <div v-for="dim in dimensions" :key="dim.key" class="factor-item">
            <span>{{ dim.label }}</span>
            <div class="score-bar">
              <div class="bar" style="width:100px">
                <div class="bar-fill" :style="barStyle(detail.score[dim.key])"></div>
              </div>
              <span class="val">{{ fmt(detail.score[dim.key]) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3 style="margin-bottom:12px">因子明细 ({{ detail.factors.length }} 个)</h3>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>因子代码</th>
                <th>原始值</th>
                <th>归一化分</th>
                <th>数据溯源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in detail.factors" :key="f.factor_code">
                <td><span class="factor-code">{{ f.factor_code }}</span></td>
                <td>{{ f.raw_value != null ? f.raw_value.toFixed(4) : '-' }}</td>
                <td>
                  <div class="score-bar">
                    <div class="bar"><div class="bar-fill" :style="barStyle(f.score)"></div></div>
                    <span class="val">{{ f.score != null ? f.score.toFixed(1) : '-' }}</span>
                  </div>
                </td>
                <td style="font-size:11px;color:var(--text-secondary);max-width:300px;overflow:hidden;text-overflow:ellipsis">
                  {{ f.lineage }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { getCompanyScore } from '../api'

use([RadarChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const loading = ref(false)
const detail = ref(null)

const dimensions = [
  { key: 'survival', label: '生存力' },
  { key: 'replication', label: '复制力' },
  { key: 'adaptation', label: '适应力' },
  { key: 'moat', label: '优势积累' },
  { key: 'valuation', label: '估值纪律' },
]

const fmt = (v) => v != null ? v.toFixed(1) : '-'

const barStyle = (v) => {
  const pct = Math.min(100, Math.max(0, v || 0))
  const color = pct >= 75 ? '#34a853' : pct >= 55 ? '#fbbc04' : '#ea4335'
  return { width: pct + '%', background: color }
}

const radarOption = computed(() => {
  if (!detail.value) return {}
  const s = detail.value.score
  return {
    tooltip: {},
    radar: {
      indicator: dimensions.map(d => ({ name: d.label, max: 100 })),
      shape: 'polygon',
      splitNumber: 4,
    },
    series: [{
      type: 'radar',
      data: [{
        value: dimensions.map(d => s[d.key] || 0),
        name: '维度得分',
        areaStyle: { opacity: 0.2 },
        lineStyle: { width: 2 },
      }],
    }],
  }
})

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await getCompanyScore(route.params.id, { model: 'balanced' })
    detail.value = data
  } catch (e) {
    console.error(e)
  }
  loading.value = false
})
</script>
