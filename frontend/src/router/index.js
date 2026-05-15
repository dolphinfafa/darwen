import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
  // V2 三层漏斗筛选
  { path: '/', redirect: '/universe' },
  { path: '/universe', name: 'UniverseConfig', component: () => import('../views/UniverseConfig.vue') },
  { path: '/config', name: 'ScreenConfig', component: () => import('../views/ScreenConfig.vue') },
  { path: '/run/:runId', name: 'ScreenRun', component: () => import('../views/ScreenRun.vue') },
  { path: '/results/:runId', name: 'ScreenResults', component: () => import('../views/ScreenResults.vue') },
  { path: '/my-runs', name: 'MyRuns', component: () => import('../views/MyRuns.vue') },
  { path: '/run/:runId/company/:companyId', name: 'CompanyDetailV2', component: () => import('../views/CompanyDetailV2.vue') },
  { path: '/account', name: 'AccountSettings', component: () => import('../views/AccountSettings.vue') },
  // 保留 admin
  { path: '/admin', name: 'Admin', component: () => import('../views/Admin.vue'), meta: { admin: true } },
]

const router = createRouter({
  history: createWebHistory('/darwen/'),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('darwen_token')
  if (!to.meta.public && !token) return next({ name: 'Login' })
  if (to.meta.admin) {
    try {
      const user = JSON.parse(localStorage.getItem('darwen_user') || '{}')
      if (!user.is_admin) return next({ name: 'UniverseConfig' })
    } catch {
      return next({ name: 'UniverseConfig' })
    }
  }
  next()
})

export default router
