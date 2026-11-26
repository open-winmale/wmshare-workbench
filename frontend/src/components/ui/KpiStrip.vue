<script setup lang="ts">
/** KPI 丝带：响应式瓦片，均衡分配（7 个容 5 列 → 4+3，不是 5+2）。 */
import { computed } from 'vue'

export interface Kpi {
  key: string
  label: string
  value: number | string
  tone?: 'ok' | 'warn' | 'bad' | 'muted'
  hint?: string
}

const props = defineProps<{ items: Kpi[] }>()

/**
 * 均衡拆行。flex-wrap 的贪心换行会排出 5+2 这种头重脚轻（docstring 曾
 * 声称 4+3 但代码从没实现，P5-03 把它做真）：超过单行容量的瓦片一律
 * 对半拆成两行。≤5 个保持单行——两三张瓦片也拆两行只会浪费竖向空间。
 */
const rows = computed<Kpi[][]>(() => {
  const n = props.items.length
  if (n <= 5) {
    return [props.items]
  }
  const half = Math.ceil(n / 2)
  return [props.items.slice(0, half), props.items.slice(half)]
})
</script>

<template>
  <div class="strip">
    <div v-for="(row, i) in rows" :key="i" class="row">
      <div v-for="k in row" :key="k.key" class="tile" :title="k.hint">
        <span class="label">{{ k.label }}</span>
        <span class="value" :class="k.tone ?? 'muted'">{{ k.value }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strip {
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-4);
  padding: var(--wb-sp-5) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--wb-sp-5);
}

.tile {
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-1);
  min-width: 88px;
}

.label {
  font-size: var(--wb-fs-1);
  color: var(--wb-text-tertiary);
}

.value {
  font-family: var(--wb-font-mono);
  font-size: var(--wb-fs-6);
  font-variant-numeric: tabular-nums;
}

.value.ok {
  color: var(--wb-down);
}

.value.warn {
  color: var(--wb-warning);
}

.value.bad {
  color: var(--wb-up);
}

.value.muted {
  color: var(--wb-text-tertiary);
}
</style>
