import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Screener', component: () => import('../views/Screener.vue') },
  { path: '/company/:id', name: 'CompanyDetail', component: () => import('../views/CompanyDetail.vue') },
  { path: '/report', name: 'BatchReport', component: () => import('../views/BatchReport.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
