import axios from 'axios'

// 不写死 /v1，各函数完整路径，便于 V1 + V2 共存
const api = axios.create({
  baseURL: '/darwen',
  timeout: 60000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('darwen_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

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

// ───────── V1 Auth ─────────
export const sendVerifyCode = phone => api.post('/v1/auth/send-code', { phone })
export const sendCodeByUsername = username => api.post('/v1/auth/send-code-by-username', { username })
export const loginStep1 = data => api.post('/v1/auth/login', data)
export const loginVerify = data => api.post('/v1/auth/login-verify', data)
export const loginTrusted = data => api.post('/v1/auth/login-trusted', data)
export const register = data => api.post('/v1/auth/register', data)
export const getMe = () => api.get('/v1/auth/me')

// ───────── V1 User Settings ─────────
export const getApiKeyStatus = () => api.get('/v1/user/api-key/status')
export const bindApiKey = (provider, api_key, group_id) =>
  api.post('/v1/user/api-key', { provider, api_key, group_id })
export const unbindApiKey = provider =>
  api.delete('/v1/user/api-key', { data: { provider } })
export const setDefaultProvider = provider =>
  api.patch('/v1/user/ai-provider-default', { provider })

// ───────── V2 Screening ─────────
export const getUniversePresets = () => api.get('/v2/universe/presets')
export const createScreenRun = body => api.post('/v2/screen-run', body)
export const getScreenRunStatus = runId => api.get(`/v2/screen-run/${runId}`)
export const getScreenRunResults = (runId, perBucketLimit = 50) =>
  api.get(`/v2/screen-run/${runId}/results`, { params: { per_bucket_limit: perBucketLimit } })
export const getCompanyDetail = (runId, companyId) =>
  api.get(`/v2/screen-run/${runId}/result/${companyId}`)

export default api
