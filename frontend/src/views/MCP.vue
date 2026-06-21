<template>
  <div class="page">
    <h1>MCP 接入</h1>
    <p class="hint">把 Darwen 接入你的 AI agent（Claude 等）。配置后，agent 可读取你「我的股票池」每只股票的
      最新收盘价与市盈率(TTM)，在股价跌到你满意的价位时主动提醒你买入。</p>

    <section class="card">
      <h2>① 这是什么</h2>
      <p class="sub">Darwen 提供一个远程 <b>MCP（Model Context Protocol）</b> 服务。Claude 连上后多了一个工具
        <code>list_watchlist_quotes</code>，能实时读你股票池的行情。你只需在对话里说「××跌到 ×× 提醒我」，
        Claude 会读取最新价并判断是否到价——目标价和提醒逻辑都由 Claude 处理，Darwen 只负责提供数据。</p>
    </section>

    <section class="card">
      <h2>② 连接信息</h2>
      <p class="row">
        <span class="lbl">MCP URL</span>
        <code class="tok">{{ mcpUrl || '—' }}</code>
        <button class="copy" @click="copy(mcpUrl)">复制</button>
      </p>
      <p class="row">
        <span class="lbl">访问令牌</span>
        <template v-if="mcpToken">
          <code class="tok new">{{ mcpToken }}</code>
          <button class="copy" @click="copy(mcpToken)">复制</button>
          <span class="once">⚠ 仅此一次显示，请立即保存</span>
        </template>
        <template v-else>
          <span class="muted">{{ mcpHasToken ? '已生成（明文不可再查，可重新生成覆盖）' : '尚未生成' }}</span>
        </template>
      </p>
      <button class="gen" :disabled="genning" @click="genMcp">
        {{ genning ? '生成中…' : (mcpHasToken ? '重新生成令牌' : '生成令牌') }}
      </button>
    </section>

    <section class="card">
      <h2>③ 在 Claude 里配置（远程 MCP）</h2>
      <p class="sub">在 Claude 桌面端/网页的「连接器 / Connectors」添加一个自定义远程 MCP：</p>
      <ul class="steps">
        <li>类型：<b>远程 / Streamable HTTP</b></li>
        <li>URL：填上面的 <b>MCP URL</b></li>
        <li>鉴权头：<code>Authorization: Bearer &lt;你的访问令牌&gt;</code></li>
      </ul>
      <p class="sub">配置完成后，问 Claude「看看我股票池现在的价格和市盈率」即可验证。</p>
    </section>

    <div v-if="msg" class="msg" :class="msgType">{{ msg }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getMcpTokenStatus, createMcpToken } from '../api'

const mcpHasToken = ref(false)
const mcpToken = ref('')
const mcpUrl = ref('')
const genning = ref(false)
const msg = ref('')
const msgType = ref('')

function urlFrom(data) {
  // 后端配了公网基址（dev/prod 各自 .env）则用完整 URL；否则按当前访问域名动态拼
  return data.mcp_url || (window.location.origin + data.mcp_path)
}

async function refreshMcp() {
  try {
    const { data } = await getMcpTokenStatus()
    mcpHasToken.value = data.has_token
    mcpUrl.value = urlFrom(data)
  } catch (e) {
    msg.value = e.response?.data?.detail || e.message
    msgType.value = 'err'
  }
}

async function genMcp() {
  if (mcpHasToken.value && !confirm('重新生成会使旧令牌立即失效，确认？')) return
  genning.value = true
  msg.value = ''
  try {
    const { data } = await createMcpToken()
    mcpToken.value = data.token
    mcpUrl.value = urlFrom(data)
    mcpHasToken.value = true
    msg.value = '令牌已生成，请立即复制保存'
    msgType.value = 'ok'
  } catch (e) {
    msg.value = e.response?.data?.detail || e.message
    msgType.value = 'err'
  } finally {
    genning.value = false
  }
}

function copy(t) {
  if (!t) return
  navigator.clipboard?.writeText(t)
  msg.value = '已复制到剪贴板'
  msgType.value = 'ok'
}

onMounted(refreshMcp)
</script>

<style scoped>
.page { padding: 24px; max-width: 760px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 16px; line-height: 1.6; }
.card { padding: 18px; border: 1px solid #e0e0e8; border-radius: 10px; background: #fff; margin-bottom: 16px; }
.card h2 { margin: 0 0 10px; font-size: 1.05rem; }
.sub { color: #555; font-size: 0.88rem; line-height: 1.7; margin: 0 0 8px; }
.sub code, .steps code { background: #f0f0f5; padding: 1px 6px; border-radius: 4px; font-size: 0.82rem; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
.row .lbl { width: 72px; color: #8888a0; font-size: 0.85rem; }
.tok { background: #f0f0f5; padding: 3px 10px; border-radius: 5px; font-size: 0.82rem; word-break: break-all; flex: 1; min-width: 200px; }
.tok.new { background: #fff7e6; color: #b06000; }
.once { color: #c0392b; font-size: 0.78rem; }
.copy { padding: 4px 12px; border: 1px solid #4285f4; background: #fff; color: #4285f4; border-radius: 5px; cursor: pointer; font-size: 0.8rem; }
.gen { margin-top: 8px; padding: 8px 18px; border-radius: 6px; background: #4285f4; color: #fff; border: none; cursor: pointer; }
.gen:disabled { background: #ccc; cursor: not-allowed; }
.steps { margin: 6px 0; padding-left: 20px; color: #555; font-size: 0.88rem; line-height: 1.9; }
.muted { color: #8888a0; font-size: 0.86rem; }
.msg { padding: 10px; border-radius: 6px; margin-top: 12px; }
.msg.ok { background: #d6f5e0; color: #176b3a; }
.msg.err { background: #fef0f0; color: #c00; }
</style>
