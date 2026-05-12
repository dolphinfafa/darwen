<template>
  <nav v-if="!isLoginPage" class="nav">
    <router-link to="/" class="nav-brand">Darwen V2</router-link>
    <router-link to="/universe">新建筛选</router-link>
    <router-link to="/account">账户设置</router-link>
    <router-link v-if="currentUser?.is_admin" to="/admin">管理</router-link>
    <span class="nav-spacer"></span>
    <span v-if="currentUser" class="nav-user">
      {{ currentUser.username }}
      <button class="logout-btn" @click="logout">退出</button>
    </span>
  </nav>
  <router-view />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isLoginPage = computed(() => route.name === 'Login')

const currentUser = ref(null)

function loadUser() {
  try {
    const raw = localStorage.getItem('darwen_user')
    currentUser.value = raw ? JSON.parse(raw) : null
  } catch { currentUser.value = null }
}

watch(() => route.path, loadUser, { immediate: true })

function logout() {
  localStorage.removeItem('darwen_token')
  localStorage.removeItem('darwen_user')
  currentUser.value = null
  router.push('/login')
}
</script>

<style scoped>
.nav-spacer { flex: 1; }
.nav-user {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary, #8888a0);
}
.logout-btn {
  padding: 4px 10px;
  border: 1px solid var(--border, #e0e0e8);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary, #8888a0);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}
.logout-btn:hover {
  border-color: #ea4335;
  color: #ea4335;
}
</style>
