<template>
  <div>
    <div style="margin-bottom:16px">
      <router-link to="/" class="btn">&larr; 返回筛选</router-link>
    </div>

    <h2 style="margin-bottom:16px">回测与验证系统</h2>

    <!-- 参数面板 -->
    <div class="card" style="margin-bottom:16px">
      <div class="filters">
        <select v-model="params.market">
          <option value="US">美股</option>
          <option value="CN_A">A股</option>
        </select>
        <select v-model="params.model">
          <option value="balanced">基准</option>
          <option value="conservative">保守</option>
          <option value="aggressive">激进</option>
        </select>
        <input v-model.number="params.start_year" type="number" min="2012" max="2024" style="width:80px" />
        <span>至</span>
        <input v-model.number="params.end_year" type="number" min="2013" max="2025" style="width:80px" />
        <button class="btn btn-primary" @click="runAll" :disabled="loading">
          {{ loading ? '计算中...' : '运行回测' }}
        </button>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar" v-if="hasData">
      <button v-for="t in tabs" :key="t.key" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <div v-if="loading" class="loading">正在计算回测...</div>

    <!-- 1. 组合表现 -->
    <div v-if="activeTab === 'portfolio' && portfolio" class="card">
      <h3>组合表现（Top 20% 等权 vs 全市场）</h3>
      <div class="metrics-grid">
        <div class="metric-card accent">
          <div class="metric-val">{{ portfolio.metrics.cagr }}%</div>
          <div class="metric-label">年化收益 CAGR</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{{ portfolio.metrics.alpha }}%</div>
          <div class="metric-label">超额收益 Alpha</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{{ portfolio.metrics.sharpe }}</div>
          <div class="metric-label">夏普比率</div>
        </div>
        <div class="metric-card warn">
          <div class="metric-val">{{ portfolio.metrics.max_drawdown }}%</div>
          <div class="metric-label">最大回撤</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{{ portfolio.metrics.volatility }}%</div>
          <div class="metric-label">波动率</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{{ portfolio.metrics.win_rate }}%</div>
          <div class="metric-label">胜率</div>
        </div>
      </div>
      <div style="margin-top:16px">
        <v-chart :option="portfolioChartOption" autoresize style="height:400px" />
      </div>
    </div>

    <!-- 2. 分层验证 -->
    <div v-if="activeTab === 'quintile' && quintile" class="card">
      <h3>
        分层验证（{{ quintile.params.n_groups }} 档）
        <span :class="quintile.monotonic ? 'verdict-pass' : 'verdict-fail'">
          {{ quintile.monotonic ? 'PASS 单调性成立' : 'FAIL 单调性不成立' }}
        </span>
      </h3>
      <div style="margin-top:16px">
        <v-chart :option="quintileBarOption" autoresize style="height:350px" />
      </div>
      <div style="margin-top:16px">
        <table>
          <thead>
            <tr>
              <th>分组</th>
              <th>年化收益</th>
              <th>累计收益</th>
              <th>CAGR</th>
              <th>夏普</th>
              <th>胜率</th>
              <th>最好/最差</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, label) in quintile.summary" :key="label">
              <td style="font-weight:600">{{ label }}</td>
              <td>{{ s.avg_annual_return }}%</td>
              <td>{{ s.cumulative_return }}%</td>
              <td>{{ s.cagr }}%</td>
              <td>{{ s.sharpe }}</td>
              <td>{{ s.win_rate }}%</td>
              <td style="font-size:12px">{{ s.max_return }}% / {{ s.min_return }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. 因子 IC -->
    <div v-if="activeTab === 'ic' && factorIC" class="card">
      <h3>因子有效性分析（IC / ICIR）</h3>
      <div style="margin-top:16px">
        <v-chart :option="icBarOption" autoresize style="height:400px" />
      </div>
      <div style="margin-top:16px">
        <table>
          <thead>
            <tr>
              <th>因子</th>
              <th>IC均值</th>
              <th>ICIR</th>
              <th>正比例</th>
              <th>评价</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in factorIC.ranking" :key="r.factor">
              <td><span class="factor-code">{{ r.factor }}</span></td>
              <td :style="{ color: r.ic_mean > 0 ? '#34a853' : '#ea4335' }">{{ r.ic_mean }}</td>
              <td>{{ r.icir }}</td>
              <td>{{ r.positive_ratio }}%</td>
              <td>
                <span :class="'verdict-badge verdict-' + r.verdict.toLowerCase()">{{ r.verdict }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 4. 稳定性 -->
    <div v-if="activeTab === 'stability' && stability" class="card">
      <h3>评分稳定性分析</h3>
      <div class="metrics-grid" style="margin-bottom:16px">
        <div class="metric-card">
          <div class="metric-val">{{ stability.avg_score_volatility }}</div>
          <div class="metric-label">平均评分波动</div>
        </div>
        <div class="metric-card accent">
          <div class="metric-val">{{ stability.persistence_rate }}%</div>
          <div class="metric-label">Top 留存率</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{{ stability.total_companies_tracked }}</div>
          <div class="metric-label">跟踪公司数</div>
        </div>
      </div>

      <h4 style="margin:12px 0 8px">分层迁移矩阵</h4>
      <table style="max-width:400px">
        <thead>
          <tr>
            <th>From \ To</th>
            <th>Top</th>
            <th>Watch</th>
            <th>Reject</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="from_tier in ['Top','Watch','Reject']" :key="from_tier">
            <td style="font-weight:600">{{ from_tier }}</td>
            <td v-for="to_tier in ['Top','Watch','Reject']" :key="to_tier">
              {{ stability.tier_transitions[from_tier]?.[to_tier] || 0 }}
            </td>
          </tr>
        </tbody>
      </table>

      <h4 style="margin:16px 0 8px">Top 公司评分追踪</h4>
      <div>
        <v-chart :option="stabilityChartOption" autoresize style="height:400px" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DataZoomComponent, MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import api from '../api'

use([
  LineChart, BarChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DataZoomComponent, MarkLineComponent,
  CanvasRenderer,
])

const tabs = [
  { key: 'portfolio', label: '组合表现' },
  { key: 'quintile', label: '分层验证' },
  { key: 'ic', label: '因子分析' },
  { key: 'stability', label: '稳定性' },
]
const activeTab = ref('portfolio')
const loading = ref(false)

const params = reactive({ market: 'US', model: 'balanced', start_year: 2013, end_year: 2024 })

const portfolio = ref(null)
const quintile = ref(null)
const factorIC = ref(null)
const stability = ref(null)

const hasData = computed(() => portfolio.value || quintile.value || factorIC.value || stability.value)

async function runAll() {
  loading.value = true
  const p = { start_year: params.start_year, end_year: params.end_year, model: params.model, market: params.market }
  try {
    const [r1, r2, r3, r4] = await Promise.all([
      api.get('/backtest-v2/portfolio', { params: p }),
      api.get('/backtest-v2/quintile', { params: p }),
      api.get('/backtest-v2/factor-ic', { params: { start_year: p.start_year, end_year: p.end_year, market: p.market } }),
      api.get('/backtest-v2/stability', { params: { model: p.model, market: p.market } }),
    ])
    portfolio.value = r1.data
    quintile.value = r2.data
    factorIC.value = r3.data
    stability.value = r4.data
  } catch (e) {
    console.error(e)
  }
  loading.value = false
}

// ── 图表配置 ──

const portfolioChartOption = computed(() => {
  if (!portfolio.value) return {}
  const c = portfolio.value.curve
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['策略（Top 20%）', '基准（全市场）'], bottom: 0 },
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    xAxis: { type: 'category', data: c.map(d => d.date.substring(0, 7)) },
    yAxis: [
      { type: 'value', name: '净值', min: v => Math.floor(v.min * 10) / 10 },
    ],
    series: [
      {
        name: '策略（Top 20%）', type: 'line', data: c.map(d => d.portfolio),
        lineStyle: { width: 2.5 }, itemStyle: { color: '#1a73e8' }, showSymbol: true, symbolSize: 6,
      },
      {
        name: '基准（全市场）', type: 'line', data: c.map(d => d.benchmark),
        lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: '#999' }, showSymbol: true, symbolSize: 4,
      },
    ],
  }
})

const quintileBarOption = computed(() => {
  if (!quintile.value) return {}
  const s = quintile.value.summary
  const labels = Object.keys(s)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 30, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', name: '年化收益 (%)' },
    series: [{
      type: 'bar',
      data: labels.map((l, i) => ({
        value: s[l].avg_annual_return,
        itemStyle: { color: i === 0 ? '#1a73e8' : i === labels.length - 1 ? '#ea4335' : '#aab' },
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', formatter: '{c}%', fontSize: 12 },
    }],
  }
})

const icBarOption = computed(() => {
  if (!factorIC.value) return {}
  const ranking = factorIC.value.ranking
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 30, bottom: 80 },
    xAxis: {
      type: 'category', data: ranking.map(r => r.factor),
      axisLabel: { rotate: 45, fontSize: 11 },
    },
    yAxis: { type: 'value', name: 'IC 均值' },
    series: [{
      type: 'bar',
      data: ranking.map(r => ({
        value: r.ic_mean,
        itemStyle: { color: r.ic_mean > 0.05 ? '#34a853' : r.ic_mean > 0 ? '#fbbc04' : '#ea4335' },
      })),
      barWidth: '60%',
    }],
  }
})

const stabilityChartOption = computed(() => {
  if (!stability.value) return {}
  const top5 = stability.value.top_companies.slice(0, 8)
  const colors = ['#1a73e8', '#ea4335', '#34a853', '#fbbc04', '#9334e6', '#ff6d01', '#46bdc6', '#e91e63']
  // 合并所有日期
  const allDates = [...new Set(top5.flatMap(c => c.scores.map(s => s.date)))].sort()
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: top5.map(c => c.name.substring(0, 15)), bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 50, right: 30, top: 20, bottom: 60 },
    xAxis: { type: 'category', data: allDates.map(d => d.substring(0, 4)) },
    yAxis: { type: 'value', name: '总分', min: 30, max: 85 },
    series: top5.map((c, i) => ({
      name: c.name.substring(0, 15),
      type: 'line',
      data: allDates.map(d => {
        const s = c.scores.find(s => s.date === d)
        return s ? s.total : null
      }),
      connectNulls: true,
      lineStyle: { width: 1.5 },
      itemStyle: { color: colors[i % colors.length] },
      symbolSize: 4,
    })),
  }
})
</script>

<style scoped>
.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 2px solid var(--border, #dadce0);
}
.tab-bar button {
  padding: 10px 20px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}
.tab-bar button.active {
  color: var(--primary, #1a73e8);
  border-bottom-color: var(--primary, #1a73e8);
  font-weight: 600;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.metric-card {
  padding: 14px 16px;
  border: 1px solid var(--border, #dadce0);
  border-radius: 8px;
  text-align: center;
}
.metric-card.accent { border-color: var(--primary, #1a73e8); background: rgba(26,115,232,0.04); }
.metric-card.warn { border-color: #ea4335; background: rgba(234,67,53,0.04); }
.metric-val { font-size: 22px; font-weight: 700; color: var(--text); }
.metric-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

.verdict-pass { font-size: 12px; color: #137333; background: #e6f4ea; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }
.verdict-fail { font-size: 12px; color: #c5221f; background: #fce8e6; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }

.verdict-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.verdict-strong { color: #137333; background: #e6f4ea; }
.verdict-moderate { color: #b06000; background: #fef7e0; }
.verdict-weak { color: #5f6368; background: #f1f3f4; }
.verdict-ineffective { color: #c5221f; background: #fce8e6; }
</style>
