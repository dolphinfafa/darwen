import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'Screener', component: () => import('../views/Screener.vue') },
  { path: '/company/:id', name: 'CompanyDetail', component: () => import('../views/CompanyDetail.vue') },
  { path: '/report', name: 'BatchReport', component: () => import('../views/BatchReport.vue') },
  { path: '/backtest', name: 'Backtest', component: () => import('../views/BacktestV2.vue') },
  { path: '/admin', name: 'Admin', component: () => import('../views/Admin.vue'), meta: { admin: true } },
]

const router = createRouter({
  history: createWebHistory('/darwen/'),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('darwen_token')

  // 未登录 → 登录页
  if (!to.meta.public && !token) {
    return next({ name: 'Login' })
  }

  // 管理员页面 → 检查权限
  if (to.meta.admin) {
    try {
      const user = JSON.parse(localStorage.getItem('darwen_user') || '{}')
      if (!user.is_admin) return next({ name: 'Screener' })
    } catch {
      return next({ name: 'Screener' })
    }
  }

  next()
})

export default router
