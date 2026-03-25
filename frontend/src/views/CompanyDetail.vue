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
          <div v-for="dim in dimensions" :key="dim.key" class="dim-section">
            <div class="dim-header" @click="toggleDim(dim.key)">
              <div class="dim-label-row">
                <span class="dim-expand-icon">{{ expandedDim === dim.key ? '▾' : '▸' }}</span>
                <span class="dim-label">{{ dim.label }}</span>
                <span class="info-icon" @click.stop="showInfo(dim)" title="查看说明">i</span>
              </div>
              <div class="score-bar">
                <div class="bar" style="width:100px">
                  <div class="bar-fill" :style="barStyle(detail.score[dim.key])"></div>
                </div>
                <span class="val">{{ fmt(detail.score[dim.key]) }}</span>
              </div>
            </div>

            <!-- 展开的因子列表 -->
            <div v-if="expandedDim === dim.key" class="dim-factors">
              <div v-for="f in getFactorsForDim(dim.key)" :key="f.factor_code" class="dim-factor-row">
                <div class="dim-factor-info">
                  <span class="factor-code">{{ f.factor_code }}</span>
                  <span class="factor-name">{{ factorMeta[f.factor_code]?.name || '' }}</span>
                </div>
                <div class="dim-factor-values">
                  <span class="factor-raw" :title="'原始值: ' + (f.raw_value != null ? f.raw_value.toFixed(6) : 'N/A')">
                    {{ f.raw_value != null ? fmtRaw(f.raw_value) : '-' }}
                  </span>
                  <div class="score-bar">
                    <div class="bar" style="width:60px"><div class="bar-fill" :style="barStyle(f.score)"></div></div>
                    <span class="val">{{ f.score != null ? f.score.toFixed(1) : '-' }}</span>
                  </div>
                </div>
              </div>
              <div v-if="getFactorsForDim(dim.key).length === 0" class="dim-factor-empty">暂无因子数据</div>
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
                <th>因子</th>
                <th>名称</th>
                <th>原始值</th>
                <th>归一化分</th>
                <th>数据溯源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in detail.factors" :key="f.factor_code">
                <td><span class="factor-code">{{ f.factor_code }}</span></td>
                <td>{{ factorMeta[f.factor_code]?.name || '-' }}</td>
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

      <!-- 维度说明弹窗 -->
      <div v-if="infoModal" class="modal-overlay" @click.self="infoModal = null">
        <div class="modal-content">
          <div class="modal-header">
            <h3>{{ infoModal.label }}</h3>
            <button class="modal-close" @click="infoModal = null">&times;</button>
          </div>
          <div class="modal-body">
            <p class="modal-desc">{{ infoModal.desc }}</p>
            <h4>包含因子</h4>
            <div class="modal-factor-list">
              <div v-for="fc in infoModal.factorCodes" :key="fc" class="modal-factor-item">
                <span class="factor-code">{{ fc }}</span>
                <span>{{ factorMeta[fc]?.name || '' }}</span>
                <span class="modal-factor-desc">{{ factorMeta[fc]?.desc || '' }}</span>
              </div>
            </div>
            <h4 style="margin-top:16px">权重分配</h4>
            <div class="modal-weights">
              <div v-for="fc in infoModal.factorCodes" :key="fc" class="modal-weight-row">
                <span class="factor-code" style="width:30px">{{ fc }}</span>
                <div class="weight-bar-bg">
                  <div class="weight-bar-fill" :style="{ width: (factorMeta[fc]?.weight * 100 || 0) + '%' }"></div>
                </div>
                <span style="font-size:12px;min-width:36px">{{ ((factorMeta[fc]?.weight || 0) * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
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
const expandedDim = ref(null)
const infoModal = ref(null)

const dimensions = [
  {
    key: 'survival',
    label: '生存力',
    desc: '评估公司在逆境中存活的能力。关注杠杆水平、流动性储备、现金流质量和融资稀释风险。高分意味着公司即使面临经济衰退或行业冲击，仍有足够的财务缓冲来维持运营。',
    factors: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
  },
  {
    key: 'replication',
    label: '复制力',
    desc: '衡量公司持续复制高质量增长的能力。核心指标是资本回报率（ROIC）和增长可持续性。高分表示公司不仅在增长，而且增长是高回报的、稳定的，管理层的承诺与实际结果一致。',
    factors: ['R1', 'R2', 'R3', 'R4', 'R5', 'R6'],
  },
  {
    key: 'adaptation',
    label: '适应力',
    desc: '衡量公司在外部冲击下的韧性和恢复能力。关注利润弹性、毛利稳定性、研发投入、业务集中度和公司治理质量。高分表示公司能够快速适应环境变化，化危为机。',
    factors: ['A1', 'A2', 'A3', 'A4', 'A5', 'A6'],
  },
  {
    key: 'moat',
    label: '优势积累',
    desc: '评估公司的护城河宽度和深度。包括定价权、复利可持续性、市场地位、规模效应、反脆弱能力和执行一致性。高分意味着公司具有难以复制的竞争优势，且优势在不断加强。',
    factors: ['M1', 'M2', 'M3', 'M4', 'M5', 'M6'],
  },
  {
    key: 'valuation',
    label: '估值纪律',
    desc: '确保不会在估值过高时买入。综合考虑估值倍数、安全边际、增长动量、回撤买点、估值安全度和交易流动性。高分表示当前估值具有吸引力，下行风险有限。',
    factors: ['V1', 'V2', 'V3', 'V4', 'V5', 'V6'],
  },
]

// 因子元数据：名称、说明、维度内权重
const factorMeta = {
  S1: { name: '杠杆与偿债', dim: 'survival', weight: 0.18, desc: '利息保障倍数 + Net Debt/EBITDA，越低越安全' },
  S2: { name: '流动性缓冲', dim: 'survival', weight: 0.12, desc: '流动比率 + 现金比率，衡量短期偿债能力' },
  S3: { name: '现金流韧性', dim: 'survival', weight: 0.12, desc: 'FCF Margin + OCF波动率 + 股价波动率' },
  S4: { name: '盈利质量', dim: 'survival', weight: 0.14, desc: 'OCF/净利润，衡量利润的现金含量' },
  S5: { name: '稀释压力', dim: 'survival', weight: 0.10, desc: '3年股本变化率，越低越好' },
  S6: { name: '风险事件', dim: 'survival', weight: 0.14, desc: '3年内8-K重大事件申报数量' },
  R1: { name: '长期ROIC', dim: 'replication', weight: 0.20, desc: '5年平均投入资本回报率' },
  R2: { name: '增量ROIC', dim: 'replication', weight: 0.14, desc: '新增投入资本的边际回报率' },
  R3: { name: '收入增长', dim: 'replication', weight: 0.14, desc: '5年收入CAGR + 增长波动率' },
  R4: { name: '成本结构', dim: 'replication', weight: 0.12, desc: '毛利率 + SGA费用率' },
  R5: { name: '资本配置', dim: 'replication', weight: 0.20, desc: '再投资率 + 分红回购' },
  R6: { name: '信号一致性', dim: 'replication', weight: 0.20, desc: '收入/利润/现金流增长方向一致性' },
  A1: { name: '利润弹性', dim: 'adaptation', weight: 0.18, desc: '营业利润年度最大跌幅' },
  A2: { name: '毛利稳定', dim: 'adaptation', weight: 0.18, desc: '毛利率历年波动系数' },
  A3: { name: '研发效率', dim: 'adaptation', weight: 0.14, desc: '研发费用占收入比' },
  A4: { name: '集中度风险', dim: 'adaptation', weight: 0.16, desc: '收入波动率作为集中度代理' },
  A5: { name: '治理质量', dim: 'adaptation', weight: 0.18, desc: '稀释控制 + 盈利质量 + 分红意愿' },
  A6: { name: '监管合规', dim: 'adaptation', weight: 0.16, desc: '8-K事件申报占比（3年）' },
  M1: { name: '定价权', dim: 'moat', weight: 0.18, desc: '毛利率水平作为定价权代理' },
  M2: { name: '复利引擎', dim: 'moat', weight: 0.25, desc: 'ROIC × 再投资率 = 内生增长' },
  M3: { name: '市场地位', dim: 'moat', weight: 0.10, desc: '收入规模 × 增长率代理市占率' },
  M4: { name: '规模效应', dim: 'moat', weight: 0.14, desc: '收入增长 / SGA增长 > 1 = 规模杠杆' },
  M5: { name: '反脆弱', dim: 'moat', weight: 0.08, desc: '衰退期是否逆周期增加投入' },
  M6: { name: '执行一致性', dim: 'moat', weight: 0.25, desc: '收入与利润同方向变化的年份占比' },
  V1: { name: '估值倍数', dim: 'valuation', weight: 0.22, desc: '净利润/净资产/FCF 估值基础' },
  V2: { name: '安全边际', dim: 'valuation', weight: 0.20, desc: 'FCF Yield × (1+ROA) 质量调整' },
  V3: { name: '增长动量', dim: 'valuation', weight: 0.18, desc: '收入CAGR + 12-1个月价格动量' },
  V4: { name: '回撤买点', dim: 'valuation', weight: 0.12, desc: '6个月最大回撤，回撤深=买点好' },
  V5: { name: '估值安全', dim: 'valuation', weight: 0.18, desc: 'Earnings Yield + 连续亏损检测' },
  V6: { name: '交易流动性', dim: 'valuation', weight: 0.10, desc: '20日平均成交量' },
}

const fmt = (v) => v != null ? v.toFixed(1) : '-'

const fmtRaw = (v) => {
  if (v == null) return '-'
  const abs = Math.abs(v)
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (abs >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  if (abs < 0.01 && abs > 0) return v.toExponential(2)
  return v.toFixed(4)
}

const barStyle = (v) => {
  const pct = Math.min(100, Math.max(0, v || 0))
  const color = pct >= 75 ? '#34a853' : pct >= 55 ? '#fbbc04' : '#ea4335'
  return { width: pct + '%', background: color }
}

const toggleDim = (key) => {
  expandedDim.value = expandedDim.value === key ? null : key
}

const showInfo = (dim) => {
  infoModal.value = {
    label: dim.label,
    desc: dim.desc,
    factorCodes: dim.factors,
  }
}

const getFactorsForDim = (dimKey) => {
  if (!detail.value) return []
  const dim = dimensions.find(d => d.key === dimKey)
  if (!dim) return []
  const codes = new Set(dim.factors)
  return detail.value.factors.filter(f => codes.has(f.factor_code))
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

<style scoped>
/* 维度区块 */
.dim-section {
  border-bottom: 1px solid #f1f3f4;
}
.dim-section:last-child {
  border-bottom: none;
}

.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  cursor: pointer;
  transition: background 0.15s;
  border-radius: 4px;
  padding-left: 4px;
  padding-right: 4px;
}
.dim-header:hover {
  background: rgba(26, 115, 232, 0.04);
}

.dim-label-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dim-expand-icon {
  font-size: 12px;
  color: var(--text-secondary);
  width: 14px;
  text-align: center;
}

.dim-label {
  font-weight: 500;
}

/* ⓘ 图标 */
.info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid var(--text-secondary);
  font-size: 10px;
  font-weight: 700;
  font-style: italic;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  font-family: Georgia, serif;
  line-height: 1;
}
.info-icon:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: rgba(26, 115, 232, 0.08);
}

/* 展开的因子列表 */
.dim-factors {
  padding: 4px 0 8px 20px;
  animation: slideDown 0.15s ease-out;
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.dim-factor-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 4px;
  font-size: 13px;
  border-radius: 4px;
}
.dim-factor-row:hover {
  background: #f8f9fa;
}

.dim-factor-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.factor-name {
  color: var(--text-secondary);
  font-size: 12px;
}

.dim-factor-values {
  display: flex;
  align-items: center;
  gap: 12px;
}

.factor-raw {
  font-size: 12px;
  font-family: monospace;
  color: var(--text-secondary);
  min-width: 60px;
  text-align: right;
  cursor: help;
}

.dim-factor-empty {
  color: var(--text-secondary);
  font-size: 12px;
  padding: 8px 0;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.15s;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 520px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  margin: 0;
  font-size: 16px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover {
  color: var(--text);
}

.modal-body {
  padding: 16px 20px 20px;
}
.modal-body h4 {
  margin: 12px 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
}

.modal-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text);
  margin-bottom: 4px;
}

.modal-factor-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-factor-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  padding: 4px 0;
}
.modal-factor-item .factor-code {
  font-size: 12px;
  min-width: 24px;
}

.modal-factor-desc {
  color: var(--text-secondary);
  font-size: 12px;
  margin-left: auto;
}

.modal-weights {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-weight-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.weight-bar-bg {
  flex: 1;
  height: 6px;
  background: #e8eaed;
  border-radius: 3px;
  overflow: hidden;
}

.weight-bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 3px;
  transition: width 0.3s;
}
</style>
