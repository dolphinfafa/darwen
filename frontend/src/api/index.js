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

// ───────── V2 三层漏斗（funnel_v2）─────────
export const getFunnel = runId => api.get(`/v2/screen-run/${runId}/funnel`)

// ───────── V2 Reason Code 中文标签 ─────────
export const getReasonCodeLabels = () => api.get('/v2/reason-codes/labels')

// ───────── V2 我的筛选历史 ─────────
export const getMyRuns = (limit = 50) => api.get('/v2/my-runs', { params: { limit } })
export const renameRun = (runId, name) => api.patch(`/v2/my-runs/${runId}`, { name })
export const deleteRun = runId => api.delete(`/v2/my-runs/${runId}`)
export const getEvidence = (cid, docIds) =>
  api.get(`/v2/company/${cid}/evidence`, { params: { doc_ids: docIds } })

// ───────── V2 公司列表 + 行业（优化1） ─────────
export const getCompanies = (params = {}) => api.get('/v2/companies', { params })
export const getIndustries = (market = '') =>
  api.get('/v2/industries', { params: market ? { market } : {} })

// ───────── V2 手动 ingest（优化2） ─────────
export const ingestCompany = (market, code) =>
  api.post('/v2/companies/ingest', { market, code })
export const getIngestStatus = taskId =>
  api.get(`/v2/companies/ingest/${taskId}`)

// ───────── V2 公司画像 + 提示词（优化3 / 5） ─────────
export const getCompanyProfile = cid =>
  api.get(`/v2/company/${cid}/profile`)
export const getAnalysisPrompt = (cid, runId = null) =>
  api.get(`/v2/company/${cid}/analysis-prompt`, runId ? { params: { run_id: runId } } : {})

// 财报下载 URL（用 <a> 直接打开浏览器）
export const filingUrl = (cid, year, form = '10-K') =>
  `/darwen/v2/company/${cid}/filing-url?year=${year}&form=${form}`

// ───────── V2 我的股票池 watchlist ─────────
export const getWatchlists = () => api.get('/v2/watchlists')
export const createWatchlist = name => api.post('/v2/watchlists', { name })
export const renameWatchlist = (id, name) => api.patch(`/v2/watchlists/${id}`, { name })
export const deleteWatchlist = id => api.delete(`/v2/watchlists/${id}`)
export const getWatchlistDetail = id => api.get(`/v2/watchlists/${id}`)
export const removeWatchlistItem = (id, companyId) => api.delete(`/v2/watchlists/${id}/items/${companyId}`)
export const addToWatchlist = body => api.post('/v2/watchlists/add-company', body)
export const getMyStocks = () => api.get('/v2/watchlists/my-stocks')
export const removeMyStock = companyId => api.delete(`/v2/watchlists/my-stocks/${companyId}`)

// ───────── MCP 访问令牌 ─────────
export const getMcpTokenStatus = () => api.get('/v1/user/mcp-token')
export const createMcpToken = () => api.post('/v1/user/mcp-token')

export default api
