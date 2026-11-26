<script setup lang="ts">
/**
 * 五种批次法对比卡片（从 `PortfolioView` 拆出）。
 *
 * 同一份成交换批次法，已实现盈亏可以差很多——这不是 bug，是成本基础
 * 口径不同；`SPECIFIC` 需要每笔卖出带 `lot_id`。独立成组件后主视图
 * 保持在自己的行数硬限内。
 */
import { computed } from 'vue'

import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import { money } from '../../composables/format'

interface MethodRow {
  method: string
  realized?: number | null
  unrealized?: number | null
  value?: number | null
  valued?: number
  total?: number
  error?: string
}

const props = defineProps<{ methods: MethodRow[] }>()

const columns: Column[] = [
  { key: 'method', label: '批次法' },
  { key: 'realized', label: '已实现', numeric: true },
  { key: 'unrealized', label: '未实现', numeric: true },
  { key: 'value', label: '市值', numeric: true },
  { key: 'note', label: '', dim: true },
]

const rows = computed(() =>
  props.methods.map((m) => ({
    method: m.method,
    realized: m.error ? null : m.realized,
    unrealized: m.error ? null : m.unrealized,
    value: m.error ? null : m.value,
    note: m.error ? `不可用：${m.error}` : '',
  })) as unknown as Record<string, unknown>[],
)
</script>

<template>
  <div class="wb-card">
    <h2>五种批次法对比</h2>
    <p class="wb-hint">
      同一份成交换批次法，已实现盈亏可以差很多——这不是 bug，是成本基础口径不同。
      <code>SPECIFIC</code> 需要每笔卖出带 <code>lot_id</code>。
    </p>
    <DataTable :columns="columns" :rows="rows" empty-text="无对比数据">
      <template #realized="{ row }">{{ money(row.realized as number) }}</template>
      <template #unrealized="{ row }">{{ money(row.unrealized as number) }}</template>
      <template #value="{ row }">{{ money(row.value as number) }}</template>
    </DataTable>
  </div>
</template>
