/**
 * 全局 reason_code 中文映射（启动时拉一次缓存）
 *
 * 用法：
 *   import { ensureReasonLabels, formatReason } from '@/composables/useReasonLabels'
 *   onMounted(() => ensureReasonLabels())
 *   formatReason('Q3_FAIL_MEDIAN')  // { label: 'ROCE 中位低', desc: '...', ... }
 */
import { ref } from 'vue'
import { getReasonCodeLabels } from '../api'

const cache = ref(null)
const loading = ref(false)

export async function ensureReasonLabels() {
  if (cache.value) return cache.value
  if (loading.value) {
    // 等待并发请求完成
    while (loading.value) await new Promise(r => setTimeout(r, 50))
    return cache.value
  }
  loading.value = true
  try {
    const { data } = await getReasonCodeLabels()
    cache.value = data
    return data
  } catch (e) {
    cache.value = {}
    return {}
  } finally {
    loading.value = false
  }
}

/**
 * 同步查询单个 reason_code，未命中返回 fallback。
 * 如未先调 ensureReasonLabels()，第一次返回原 code。
 */
export function formatReason(code) {
  if (!cache.value) return { label: code, desc: '', layer: 'META', severity: 'info' }
  const direct = cache.value[code]
  if (direct) return direct
  // AI_*_HIGH 后缀处理
  if (code.endsWith('_HIGH')) {
    const base = cache.value[code.slice(0, -5)]
    if (base) return { ...base, label: base.label + '(高)', severity: 'error' }
  }
  return { label: code, desc: '', layer: 'META', severity: 'info' }
}

export function getCache() {
  return cache.value
}
