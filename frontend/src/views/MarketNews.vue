<template>
  <div class="page">
    <div class="hd">
      <h1>市场资讯</h1>
      <button class="btn" :disabled="loading" @click="reload">⟳ 刷新</button>
    </div>
    <p class="hint">A股全市场大盘资讯（来自 Tushare major_news）。非个股新闻——个股动态见各股详情页的「巨潮公告」。</p>

    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!news.length" class="muted">暂无资讯。</div>

    <ul v-else class="list">
      <li v-for="(n, i) in news" :key="i">
        <a :href="n.url" target="_blank" rel="noopener" class="title">{{ n.title || '(无标题)' }}</a>
        <div class="meta">
          <span class="src">{{ n.source || '—' }}</span>
          <span class="time">{{ fmtTime(n.published_at) }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getMarketNews } from '../api'

const news = ref([])
const loading = ref(true)
const error = ref('')

async function reload() {
  loading.value = true
  try {
    const { data } = await getMarketNews(60)
    news.value = data
    error.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(reload)
</script>

<style scoped>
.page { padding: 24px; max-width: 860px; margin: 0 auto; }
.hd { display: flex; align-items: center; justify-content: space-between; }
.hd h1 { margin: 0; }
.hint { color: #8888a0; font-size: 0.88rem; margin: 6px 0 16px; line-height: 1.6; }
.muted { color: #8888a0; }
.error { padding: 12px; background: #fef0f0; color: #c00; border-radius: 6px; }
.btn { padding: 6px 14px; border: 1px solid #4285f4; background: #fff; color: #4285f4; border-radius: 6px; cursor: pointer; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.list { list-style: none; padding: 0; margin: 0; }
.list li { padding: 12px 0; border-bottom: 1px solid #f0f0f5; }
.title { color: #1a3a8a; text-decoration: none; font-size: 0.95rem; font-weight: 500; line-height: 1.5; }
.title:hover { text-decoration: underline; }
.meta { margin-top: 5px; font-size: 0.78rem; color: #aaa; display: flex; gap: 12px; }
.meta .src { color: #888; }
</style>
