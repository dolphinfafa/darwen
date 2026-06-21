<template>
  <div class="page">
    <h1>账户设置</h1>
    <p class="hint">绑定 AI Provider API Key，启动筛选时将由用户自己的 key 调用。</p>

    <section class="card">
      <h2>ChatGPT</h2>
      <p v-if="status?.chatgpt_bound" class="bound">
        已绑定 · key: <code>{{ status.chatgpt_masked }}</code>
        <button class="del-btn" @click="unbind('chatgpt')">解绑</button>
      </p>
      <form v-else @submit.prevent="bind('chatgpt')">
        <label>OpenAI API Key (sk-...)
          <input type="password" v-model="chatgptKey" autocomplete="off" />
        </label>
        <button type="submit" :disabled="!chatgptKey || saving">{{ saving === 'chatgpt' ? '保存中…' : '保存' }}</button>
      </form>
    </section>

    <section class="card">
      <h2>MiniMax</h2>
      <p v-if="status?.minimax_bound" class="bound">
        已绑定 · group_id: <code>{{ status.minimax_group_id }}</code> · key: <code>{{ status.minimax_masked }}</code>
        <button class="del-btn" @click="unbind('minimax')">解绑</button>
      </p>
      <form v-else @submit.prevent="bind('minimax')">
        <label>MiniMax Group ID
          <input type="text" v-model="minimaxGroup" autocomplete="off" />
        </label>
        <label>MiniMax API Key
          <input type="password" v-model="minimaxKey" autocomplete="off" />
        </label>
        <button type="submit" :disabled="!minimaxKey || !minimaxGroup || saving">{{ saving === 'minimax' ? '保存中…' : '保存' }}</button>
      </form>
    </section>

    <section class="card">
      <h2>默认 AI Provider</h2>
      <label class="radio">
        <input type="radio" value="chatgpt" v-model="defaultProvider" @change="changeDefault" />
        ChatGPT
      </label>
      <label class="radio">
        <input type="radio" value="minimax" v-model="defaultProvider" @change="changeDefault" />
        MiniMax
      </label>
    </section>

    <div v-if="msg" class="msg" :class="msgType">{{ msg }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { bindApiKey, getApiKeyStatus, setDefaultProvider, unbindApiKey } from '../api'

const status = ref(null)
const chatgptKey = ref('')
const minimaxKey = ref('')
const minimaxGroup = ref('')
const defaultProvider = ref('chatgpt')
const saving = ref(null)  // 'chatgpt' | 'minimax' | null
const msg = ref('')
const msgType = ref('')

async function refresh() {
  const { data } = await getApiKeyStatus()
  status.value = data
  defaultProvider.value = data.default_provider
}

async function bind(provider) {
  saving.value = provider
  msg.value = ''
  try {
    if (provider === 'chatgpt') {
      const { data } = await bindApiKey('chatgpt', chatgptKey.value)
      status.value = data
      chatgptKey.value = ''
    } else {
      const { data } = await bindApiKey('minimax', minimaxKey.value, minimaxGroup.value)
      status.value = data
      minimaxKey.value = ''
      minimaxGroup.value = ''
    }
    msg.value = '绑定成功'
    msgType.value = 'ok'
  } catch (e) {
    msg.value = e.response?.data?.detail || e.message
    msgType.value = 'err'
  } finally {
    saving.value = null
  }
}

async function unbind(provider) {
  if (!confirm(`确认解绑 ${provider}?`)) return
  try {
    const { data } = await unbindApiKey(provider)
    status.value = data
    msg.value = '已解绑'
    msgType.value = 'ok'
  } catch (e) {
    msg.value = e.response?.data?.detail || e.message
    msgType.value = 'err'
  }
}

async function changeDefault() {
  try {
    const { data } = await setDefaultProvider(defaultProvider.value)
    status.value = data
    msg.value = '默认 provider 已切换'
    msgType.value = 'ok'
  } catch (e) {
    msg.value = e.response?.data?.detail || e.message
    msgType.value = 'err'
  }
}

onMounted(refresh)
</script>

<style scoped>
.page { padding: 24px; max-width: 720px; margin: 0 auto; }
.hint { color: #8888a0; margin-bottom: 16px; }
.card { padding: 18px; border: 1px solid #e0e0e8; border-radius: 10px; background: #fff; margin-bottom: 16px; }
.card h2 { margin: 0 0 12px 0; }
.bound { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.bound code { background: #f0f0f5; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }
form label { display: block; margin: 8px 0; }
form input { width: 100%; padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; }
form button {
  padding: 8px 18px; border-radius: 6px; background: #4285f4; color: #fff; border: none; cursor: pointer;
}
form button:disabled { background: #ccc; cursor: not-allowed; }
.del-btn {
  margin-left: auto; padding: 4px 10px; border: 1px solid #c00;
  background: #fff; color: #c00; border-radius: 4px; cursor: pointer;
}
.radio { font-weight: normal; display: block; margin: 8px 0; }
.radio input { margin-right: 6px; }
.sub { color: #8888a0; font-size: 0.86rem; margin: 0 0 12px; line-height: 1.6; }
.tok { background: #f0f0f5; padding: 2px 8px; border-radius: 4px; font-size: 0.82rem; word-break: break-all; }
.new-tok .tok { background: #fff7e6; color: #b06000; }
.copy { padding: 3px 10px; border: 1px solid #4285f4; background: #fff; color: #4285f4; border-radius: 5px; cursor: pointer; font-size: 0.8rem; }
.gen { margin-top: 6px; padding: 8px 18px; border-radius: 6px; background: #4285f4; color: #fff; border: none; cursor: pointer; }
.gen:disabled { background: #ccc; cursor: not-allowed; }
.msg { padding: 10px; border-radius: 6px; margin-top: 12px; }
.msg.ok { background: #d6f5e0; color: #176b3a; }
.msg.err { background: #fef0f0; color: #c00; }
</style>
