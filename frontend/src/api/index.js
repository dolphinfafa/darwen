import axios from 'axios'

const api = axios.create({
  baseURL: '/darwen/v1',
  timeout: 30000,
})

// 自动附加 JWT token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('darwen_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 自动跳转登录
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401 && !err.config.url.includes('/auth/')) {
      localStorage.removeItem('darwen_token')
      localStorage.removeItem('darwen_user')
      window.location.href = '/darwen/login'
    }
    return Promise.reject(err)
  }
)

export function getScreener(params = {}) {
  return api.get('/screener', { params })
}

export function getCompanyScore(companyId, params = {}) {
  return api.get(`/company/${companyId}/score`, { params })
}

export function getCompanyScoreV1(companyId, params = {}) {
  return api.get(`/company/${companyId}/score-v1`, { params })
}

export function getCompanyHistory(companyId, params = {}) {
  return api.get(`/company/${companyId}/history`, { params })
}

export function getCompanies(params = {}) {
  return api.get('/companies', { params })
}

export function getBatchReport(params = {}) {
  return api.get('/reports/batch', { params })
}

export function getModels() {
  return api.get('/meta/models')
}

export function getIndustries() {
  return api.get('/meta/industries')
}

// ── Auth API ─────────────────────────────
export function sendVerifyCode(phone) {
  return api.post('/auth/send-code', { phone })
}

export function sendCodeByUsername(username) {
  return api.post('/auth/send-code-by-username', { username })
}

export function loginStep1(data) {
  return api.post('/auth/login', data)
}

export function loginVerify(data) {
  return api.post('/auth/login-verify', data)
}

export function loginTrusted(data) {
  return api.post('/auth/login-trusted', data)
}

export function register(data) {
  return api.post('/auth/register', data)
}

export function getMe() {
  return api.get('/auth/me')
}

export default api
