<template>
  <div>
    <div style="margin-bottom:16px">
      <router-link to="/" class="btn">&larr; 返回筛选</router-link>
    </div>

    <h2 style="margin-bottom:16px">后台管理</h2>

    <!-- 统计卡片 -->
    <div class="stats-grid" v-if="stats">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total_users }}</div>
        <div class="stat-label">总用户数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.active_users }}</div>
        <div class="stat-label">活跃用户</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.admin_count }}</div>
        <div class="stat-label">管理员</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.verified_count }}</div>
        <div class="stat-label">已验证</div>
      </div>
    </div>

    <!-- 搜索 -->
    <div class="card" style="margin-bottom:16px">
      <div class="search-bar">
        <input v-model="searchQuery" placeholder="搜索用户名或手机号..." @keyup.enter="loadUsers" />
        <button class="btn btn-primary" @click="loadUsers">搜索</button>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="card">
      <h3 style="margin-bottom:12px">用户列表 ({{ userList.total }})</h3>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>手机号</th>
              <th>角色</th>
              <th>状态</th>
              <th>注册时间</th>
              <th>最后登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in userList.users" :key="u.id">
              <td>{{ u.id }}</td>
              <td style="font-weight:500">{{ u.username }}</td>
              <td style="font-family:monospace">{{ u.phone }}</td>
              <td>
                <span :class="u.is_admin ? 'badge badge-admin' : 'badge badge-user'">
                  {{ u.is_admin ? '管理员' : '用户' }}
                </span>
              </td>
              <td>
                <span :class="u.is_active ? 'badge badge-active' : 'badge badge-disabled'">
                  {{ u.is_active ? '正常' : '已禁用' }}
                </span>
              </td>
              <td>{{ u.created_at }}</td>
              <td>{{ u.last_login || '-' }}</td>
              <td>
                <div class="action-btns">
                  <button
                    v-if="!u.is_admin"
                    class="action-btn"
                    :class="u.is_active ? 'btn-warn' : 'btn-ok'"
                    @click="toggleActive(u)"
                  >
                    {{ u.is_active ? '禁用' : '启用' }}
                  </button>
                  <button
                    v-if="!u.is_admin"
                    class="action-btn btn-reset"
                    @click="resetPwd(u)"
                  >
                    重置密码
                  </button>
                  <button
                    v-if="!u.is_admin"
                    class="action-btn btn-del"
                    @click="deleteUser(u)"
                  >
                    删除
                  </button>
                  <span v-if="u.is_admin" style="color:var(--text-secondary);font-size:12px">—</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 重置密码弹窗 -->
    <div v-if="resetModal" class="modal-overlay" @click.self="resetModal = null">
      <div class="modal-content" style="max-width:380px">
        <div class="modal-header">
          <h3>重置密码 — {{ resetModal.username }}</h3>
          <button class="modal-close" @click="resetModal = null">&times;</button>
        </div>
        <div class="modal-body">
          <div class="field">
            <label>新密码</label>
            <input v-model="newPassword" type="text" placeholder="输入新密码（至少6位）" />
          </div>
          <button class="btn btn-primary" style="width:100%;margin-top:12px" @click="confirmResetPwd">
            确认重置
          </button>
          <p v-if="modalError" class="error-msg">{{ modalError }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const loading = ref(false)
const stats = ref(null)
const userList = ref({ total: 0, users: [] })
const searchQuery = ref('')
const resetModal = ref(null)
const newPassword = ref('')
const modalError = ref('')

async function loadStats() {
  try {
    const { data } = await api.get('/admin/stats')
    stats.value = data
  } catch {}
}

async function loadUsers() {
  loading.value = true
  try {
    const params = {}
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/admin/users', { params })
    userList.value = data
  } catch {}
  loading.value = false
}

async function toggleActive(u) {
  const action = u.is_active ? '禁用' : '启用'
  if (!confirm(`确定${action}用户 "${u.username}"？`)) return
  try {
    await api.post('/admin/users/toggle-active', { user_id: u.id, is_active: !u.is_active })
    await loadUsers()
    await loadStats()
  } catch (e) {
    alert(e.response?.data?.detail || '操作失败')
  }
}

function resetPwd(u) {
  resetModal.value = u
  newPassword.value = ''
  modalError.value = ''
}

async function confirmResetPwd() {
  modalError.value = ''
  if (!newPassword.value || newPassword.value.length < 6) {
    modalError.value = '密码至少 6 位'
    return
  }
  try {
    await api.post('/admin/users/reset-password', {
      user_id: resetModal.value.id,
      new_password: newPassword.value,
    })
    alert(`用户 ${resetModal.value.username} 密码已重置`)
    resetModal.value = null
  } catch (e) {
    modalError.value = e.response?.data?.detail || '重置失败'
  }
}

async function deleteUser(u) {
  if (!confirm(`确定删除用户 "${u.username}"？此操作不可恢复！`)) return
  try {
    await api.delete(`/admin/users/${u.id}`)
    await loadUsers()
    await loadStats()
  } catch (e) {
    alert(e.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
  loadStats()
  loadUsers()
})
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
@media (max-width: 600px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
.stat-card {
  background: var(--card, #fff);
  border: 1px solid var(--border, #dadce0);
  border-radius: 8px;
  padding: 16px 20px;
  text-align: center;
}
.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--primary, #1a73e8);
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary, #5f6368);
  margin-top: 4px;
}

.search-bar {
  display: flex;
  gap: 8px;
}
.search-bar input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border, #dadce0);
  border-radius: 8px;
  font-size: 14px;
}
.search-bar input:focus {
  outline: none;
  border-color: var(--primary, #1a73e8);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.badge-admin { background: #e8eaf6; color: #3949ab; }
.badge-user { background: #f1f3f4; color: #5f6368; }
.badge-active { background: #e6f4ea; color: #137333; }
.badge-disabled { background: #fce8e6; color: #c5221f; }

.action-btns {
  display: flex;
  gap: 6px;
  flex-wrap: nowrap;
}
.action-btn {
  padding: 4px 10px;
  border: 1px solid var(--border, #dadce0);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  background: transparent;
  white-space: nowrap;
  transition: all 0.15s;
}
.btn-warn { color: #e8a100; border-color: #e8a100; }
.btn-warn:hover { background: #e8a100; color: #fff; }
.btn-ok { color: #137333; border-color: #137333; }
.btn-ok:hover { background: #137333; color: #fff; }
.btn-reset { color: var(--primary, #1a73e8); border-color: var(--primary, #1a73e8); }
.btn-reset:hover { background: var(--primary, #1a73e8); color: #fff; }
.btn-del { color: #c5221f; border-color: #c5221f; }
.btn-del:hover { background: #c5221f; color: #fff; }

/* 复用登录页的弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #dadce0);
}
.modal-header h3 { margin: 0; font-size: 15px; }
.modal-close {
  background: none; border: none;
  font-size: 22px; cursor: pointer;
  color: var(--text-secondary);
}
.modal-body { padding: 16px 20px 20px; }
.field { margin-bottom: 12px; }
.field label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.field input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border, #dadce0);
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
}
.error-msg {
  color: #ea4335;
  font-size: 13px;
  text-align: center;
  margin-top: 8px;
}
</style>
