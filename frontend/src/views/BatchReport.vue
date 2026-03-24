<template>
  <div>
    <h2 style="margin-bottom:16px">批量报告</h2>

    <div class="filters">
      <select v-model="params.market">
        <option value="">全部市场</option>
        <option value="US">美股</option>
        <option value="CN_A">A股</option>
      </select>
      <select v-model="params.model">
        <option value="balanced">基准</option>
        <option value="conservative">保守</option>
        <option value="aggressive">激进</option>
      </select>
      <select v-model="params.tier">
        <option value="">全部分层</option>
        <option value="Top">Top</option>
        <option value="Watch">Watch</option>
        <option value="Reject">Reject</option>
      </select>
      <button class="btn btn-primary" @click="fetchReport">生成报告</button>
      <button class="btn" @click="exportCSV" v-if="report">导出 CSV</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <template v-else-if="report">
      <div class="detail-grid" style="margin-bottom:16px">
        <div class="card">
          <h3>汇总</h3>
          <p style="margin-top:8px">总计 <strong>{{ report.summary.total_companies }}</strong> 家公司</p>
          <p>权重方案: {{ report.summary.model }}</p>
        </div>
        <div class="card">
          <h3>分层分布</h3>
          <div style="display:flex;gap:16px;margin-top:8px">
            <div v-for="(count, tier) in report.summary.tier_distribution" :key="tier">
              <span :class="'tier tier-' + tier">{{ tier }}</span>
              <strong style="margin-left:4px">{{ count }}</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>公司</th>
                <th>市场</th>
                <th>行业</th>
                <th>总分</th>
                <th>分层</th>
                <th>生存力</th>
                <th>复制力</th>
                <th>适应力</th>
                <th>优势积累</th>
                <th>估值纪律</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in report.companies" :key="c.company_id"
                  @click="$router.push('/company/' + c.company_id)" style="cursor:pointer">
                <td><strong>{{ c.name }}</strong></td>
                <td>{{ c.market }}</td>
                <td>{{ c.industry || '-' }}</td>
                <td>{{ fmt(c.total) }}</td>
                <td><span :class="'tier tier-' + c.tier">{{ c.tier }}</span></td>
                <td>{{ fmt(c.survival) }}</td>
                <td>{{ fmt(c.replication) }}</td>
                <td>{{ fmt(c.adaptation) }}</td>
                <td>{{ fmt(c.moat) }}</td>
                <td>{{ fmt(c.valuation) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { getBatchReport } from '../api'

const loading = ref(false)
const report = ref(null)
const params = ref({ market: '', model: 'balanced', tier: '' })

const fmt = (v) => v != null ? v.toFixed(1) : '-'

const fetchReport = async () => {
  loading.value = true
  try {
    const p = { model: params.value.model }
    if (params.value.market) p.market = params.value.market
    if (params.value.tier) p.tier = params.value.tier
    const { data } = await getBatchReport(p)
    report.value = data
  } catch (e) {
    console.error(e)
  }
  loading.value = false
}

const exportCSV = () => {
  if (!report.value) return
  const headers = ['公司', '市场', '行业', '总分', '分层', '生存力', '复制力', '适应力', '优势积累', '估值纪律']
  const csvRows = [headers.join(',')]
  for (const c of report.value.companies) {
    csvRows.push([
      `"${c.name}"`, c.market, `"${c.industry || ''}"`,
      fmt(c.total), c.tier,
      fmt(c.survival), fmt(c.replication), fmt(c.adaptation), fmt(c.moat), fmt(c.valuation),
    ].join(','))
  }
  const blob = new Blob(['\uFEFF' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `darwen_report_${params.value.model}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>
