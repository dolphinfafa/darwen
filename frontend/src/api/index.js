import axios from 'axios'

const api = axios.create({
  baseURL: '/darwen/v1',
  timeout: 30000,
})

export function getScreener(params = {}) {
  return api.get('/screener', { params })
}

export function getCompanyScore(companyId, params = {}) {
  return api.get(`/company/${companyId}/score`, { params })
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

export default api
