<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2 class="auth-title">达尔文评分</h2>
      <p class="auth-subtitle">基于进化论的股票筛选系统</p>

      <div class="tab-switch">
        <button :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <!-- ════ 登录 ════ -->
      <form v-if="mode === 'login'" @submit.prevent="handleLogin" class="auth-form">
        <!-- 第一步：用户名 + 密码 -->
        <template v-if="loginStep === 1">
          <div class="field">
            <label>用户名</label>
            <input v-model="form.username" type="text" placeholder="请输入用户名" />
          </div>
          <div class="field">
            <label>密码</label>
            <input v-model="form.password" type="password" placeholder="请输入密码" />
          </div>
          <button type="submit" class="submit-btn" :disabled="submitting">
            {{ submitting ? '验证中...' : '登录' }}
          </button>
        </template>

        <!-- 第二步：短信验证（首次设备） -->
        <template v-if="loginStep === 2">
          <div class="verify-hint">
            <div class="verify-icon">&#128274;</div>
            <p>首次在该设备登录，需要短信验证</p>
            <p class="verify-phone">验证码已发送至 <strong>{{ maskedPhone }}</strong></p>
          </div>
          <div class="field code-field">
            <label>验证码</label>
            <div class="code-row">
              <input v-model="form.code" type="text" maxlength="6" placeholder="输入6位验证码" />
              <button type="button" class="send-btn" :disabled="countdown > 0" @click="resendCode">
                {{ countdown > 0 ? `${countdown}s` : '重新发送' }}
              </button>
            </div>
          </div>
          <button type="submit" class="submit-btn" :disabled="submitting">
            {{ submitting ? '验证中...' : '确认登录' }}
          </button>
          <button type="button" class="back-btn" @click="loginStep = 1">返回上一步</button>
        </template>
      </form>

      <!-- ════ 注册 ════ -->
      <form v-if="mode === 'register'" @submit.prevent="handleRegister" class="auth-form">
        <div class="field">
          <label>用户名</label>
          <input v-model="form.username" type="text" placeholder="请输入用户名（至少2位）" />
        </div>
        <div class="field">
          <label>手机号</label>
          <input v-model="form.phone" type="tel" maxlength="11" placeholder="请输入手机号" />
        </div>
        <div class="field">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码（至少6位）" />
        </div>
        <div class="field code-field">
          <label>验证码</label>
          <div class="code-row">
            <input v-model="form.code" type="text" maxlength="6" placeholder="短信验证码" />
            <button type="button" class="send-btn" :disabled="countdown > 0" @click="sendRegCode">
              {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </button>
          </div>
        </div>
        <button type="submit" class="submit-btn" :disabled="submitting">
          {{ submitting ? '注册中...' : '注册' }}
        </button>
      </form>

      <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {
  sendVerifyCode, sendCodeByUsername, loginStep1,
  loginVerify, loginTrusted, register,
} from '../api'

const router = useRouter()
const mode = ref('login')
const loginStep = ref(1)  // 1=用户名密码, 2=短信验证
const submitting = ref(false)
const errorMsg = ref('')
const countdown = ref(0)
const maskedPhone = ref('')

const form = reactive({
  username: '',
  phone: '',
  password: '',
  code: '',
})

let countdownTimer = null

// ── 设备指纹 ──
function getDeviceId() {
  let id = localStorage.getItem('darwen_device_id')
  if (!id) {
    id = 'dev_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10)
    localStorage.setItem('darwen_device_id', id)
  }
  return id
}

function isDeviceTrusted(username) {
  try {
    const trusted = JSON.parse(localStorage.getItem('darwen_trusted_devices') || '{}')
    return !!trusted[username]
  } catch { return false }
}

function markDeviceTrusted(username) {
  try {
    const trusted = JSON.parse(localStorage.getItem('darwen_trusted_devices') || '{}')
    trusted[username] = Date.now()
    localStorage.setItem('darwen_trusted_devices', JSON.stringify(trusted))
  } catch {}
}

// ── 通用 ──
function switchMode(m) {
  mode.value = m
  loginStep.value = 1
  errorMsg.value = ''
  form.code = ''
}

function startCountdown() {
  countdown.value = 60
  clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

function onSuccess(data, username) {
  localStorage.setItem('darwen_token', data.token)
  localStorage.setItem('darwen_user', JSON.stringify({
    username: data.username,
    is_admin: data.is_admin,
  }))
  markDeviceTrusted(username || data.username)
  router.push('/')
}

// ── 登录 ──
async function handleLogin() {
  errorMsg.value = ''

  // 第一步：用户名 + 密码
  if (loginStep.value === 1) {
    if (!form.username || !form.password) {
      errorMsg.value = '请输入用户名和密码'
      return
    }
    submitting.value = true
    try {
      // 如果设备已信任，直接登录
      if (isDeviceTrusted(form.username)) {
        const { data } = await loginTrusted({ username: form.username, password: form.password })
        onSuccess(data, form.username)
        return
      }

      // 新设备：验证密码 → 发送验证码
      const { data } = await loginStep1({ username: form.username, password: form.password })
      maskedPhone.value = data.masked_phone

      // 自动发送验证码
      try {
        const resp = await sendCodeByUsername(form.username)
        maskedPhone.value = resp.data.masked_phone || maskedPhone.value
        startCountdown()
      } catch (e) {
        errorMsg.value = e.response?.data?.detail || '验证码发送失败'
        submitting.value = false
        return
      }

      loginStep.value = 2
    } catch (e) {
      errorMsg.value = e.response?.data?.detail || '登录失败'
    }
    submitting.value = false
    return
  }

  // 第二步：提交验证码
  if (loginStep.value === 2) {
    if (!form.code) {
      errorMsg.value = '请输入验证码'
      return
    }
    submitting.value = true
    try {
      const { data } = await loginVerify({
        username: form.username,
        password: form.password,
        code: form.code,
        device_id: getDeviceId(),
      })
      onSuccess(data, form.username)
    } catch (e) {
      errorMsg.value = e.response?.data?.detail || '验证失败'
    }
    submitting.value = false
  }
}

async function resendCode() {
  errorMsg.value = ''
  try {
    const resp = await sendCodeByUsername(form.username)
    maskedPhone.value = resp.data.masked_phone || maskedPhone.value
    startCountdown()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '验证码发送失败'
  }
}

// ── 注册 ──
async function sendRegCode() {
  if (!form.phone || form.phone.length !== 11) {
    errorMsg.value = '请输入正确的11位手机号'
    return
  }
  errorMsg.value = ''
  try {
    await sendVerifyCode(form.phone)
    startCountdown()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '验证码发送失败'
  }
}

async function handleRegister() {
  errorMsg.value = ''
  if (!form.username || !form.phone || !form.password || !form.code) {
    errorMsg.value = '请填写所有字段'
    return
  }
  submitting.value = true
  try {
    const { data } = await register({
      username: form.username,
      phone: form.phone,
      password: form.password,
      code: form.code,
    })
    onSuccess(data, form.username)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '注册失败'
  }
  submitting.value = false
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary, #f5f6fa);
  padding: 20px;
}
.auth-card {
  background: var(--bg-card, #fff);
  border-radius: 16px;
  padding: 40px 36px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.08);
}
.auth-title {
  text-align: center;
  font-size: 1.6rem;
  margin: 0 0 4px;
  color: var(--text-primary, #1a1a2e);
}
.auth-subtitle {
  text-align: center;
  font-size: 0.85rem;
  color: var(--text-secondary, #8888a0);
  margin: 0 0 24px;
}
.tab-switch {
  display: flex;
  margin-bottom: 24px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border, #e0e0e8);
}
.tab-switch button {
  flex: 1;
  padding: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 0.95rem;
  color: var(--text-secondary, #8888a0);
  transition: all 0.2s;
}
.tab-switch button.active {
  background: var(--accent, #4a6cf7);
  color: #fff;
}

/* 验证提示 */
.verify-hint {
  text-align: center;
  padding: 12px 0 20px;
}
.verify-icon { font-size: 32px; margin-bottom: 8px; }
.verify-hint p {
  font-size: 0.9rem;
  color: var(--text-secondary, #8888a0);
  margin: 4px 0;
}
.verify-phone strong {
  color: var(--text-primary, #1a1a2e);
  letter-spacing: 1px;
}

.auth-form .field { margin-bottom: 16px; }
.auth-form label {
  display: block;
  font-size: 0.85rem;
  color: var(--text-secondary, #8888a0);
  margin-bottom: 6px;
}
.auth-form input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border, #e0e0e8);
  border-radius: 8px;
  font-size: 0.95rem;
  background: var(--bg-primary, #f5f6fa);
  color: var(--text-primary, #1a1a2e);
  box-sizing: border-box;
}
.auth-form input:focus {
  outline: none;
  border-color: var(--accent, #4a6cf7);
}
.code-row { display: flex; gap: 8px; }
.code-row input { flex: 1; }
.send-btn {
  white-space: nowrap;
  padding: 10px 14px;
  border: 1px solid var(--accent, #4a6cf7);
  border-radius: 8px;
  background: transparent;
  color: var(--accent, #4a6cf7);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}
.send-btn:hover:not(:disabled) { background: var(--accent, #4a6cf7); color: #fff; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.submit-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: var(--accent, #4a6cf7);
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
  margin-top: 8px;
  transition: opacity 0.2s;
}
.submit-btn:hover:not(:disabled) { opacity: 0.9; }
.submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.back-btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary, #8888a0);
  font-size: 0.9rem;
  cursor: pointer;
  margin-top: 6px;
}
.back-btn:hover { color: var(--accent, #4a6cf7); }
.error-msg {
  color: #ea4335;
  font-size: 0.85rem;
  text-align: center;
  margin-top: 12px;
}
</style>
