<template>
  <span
    class="reason-pill"
    :class="['sev-' + meta.severity, 'layer-' + meta.layer]"
    :title="meta.desc || code"
  >
    {{ meta.label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { formatReason } from '../composables/useReasonLabels'

const props = defineProps({
  code: { type: String, required: true },
})

const meta = computed(() => formatReason(props.code))
</script>

<style scoped>
.reason-pill {
  display: inline-block;
  padding: 2px 8px;
  margin: 2px;
  border-radius: 4px;
  font-size: 0.78rem;
  cursor: help;
  border: 1px solid transparent;
}
.sev-info { background: #eef3fc; color: #1f3a8a; border-color: #d6e7f5; }
.sev-warning { background: #fff4d6; color: #92500a; border-color: #ffe4cc; }
.sev-error { background: #fde0e0; color: #b30000; border-color: #fac3c3; }
.layer-AI { border-left: 3px solid #6366f1; }
.layer-Q { border-left: 3px solid #14b8a6; }
.layer-R { border-left: 3px solid #f97316; }
.layer-V { border-left: 3px solid #8b5cf6; }
</style>
