<script setup lang="ts">
/**
 * 分红分区：概览字段 + 逐次派息明细。
 *
 * 数据来自一个接口 `bonus.snapshot`（18 字段）+ `bonus.query_list`（明细）。
 * **不要改成分开调多个单项接口**：`bonus.snapshot_yield_ttm` 返回**裸 float**，
 * 按 dict 处理会静默得到 `{}`，页面就显示「—」而数据其实完全可用。
 *
 * 字段的口径（百分数 / 金额 / 文本）由**后端**在 `format` 里声明，
 * 前端不自己猜——猜错会让 0.0355 显示成 "0.04" 而不是 "3.55%"。
 */
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import { money, num, pct, price } from '../../composables/format'

export interface DividendField {
  key: string
  label: string
  value: string | number | null
  /** `pct` 小数转百分比 · `money` 元转亿/万 · `num` 两位小数 · `text` 原样 */
  format: string
}

export interface DividendRow {
  announce: string | null
  ex_date: string | null
  record_date: string | null
  sas: string | null
  dps: number | null
  payout_ratio: number | null
  ccy: string | null
}

defineProps<{
  fields: DividendField[]
  history: DividendRow[]
}>()

const columns: Column[] = [
  { key: 'announce', label: '公告日', mono: true, dim: true },
  { key: 'ex_date', label: '除权除息日', mono: true, dim: true },
  { key: 'record_date', label: '股权登记日', mono: true, dim: true },
  { key: 'sas', label: '报告期', dim: true },
  { key: 'dps', label: '每股分红', numeric: true },
  { key: 'payout_ratio', label: '派息率', numeric: true },
]

function fieldText(f: DividendField): string {
  if (f.value === null || f.value === undefined) return '—'
  if (f.format === 'pct' && typeof f.value === 'number') return pct(f.value)
  if (f.format === 'money' && typeof f.value === 'number') return money(f.value)
  if (f.format === 'num' && typeof f.value === 'number') return num(f.value)
  return String(f.value)
}
</script>

<template>
  <div>
    <h2 class="wb-h2">分红概览</h2>
    <div class="wb-kvs">
      <div v-for="f in fields" :key="f.key" class="wb-kv">
        <span>{{ f.label }}</span>
        <b>{{ fieldText(f) }}</b>
      </div>
    </div>

    <h2 class="wb-h2">逐次派息（{{ history.length }} 次）</h2>
    <DataTable :columns="columns"
               :rows="history as unknown as Record<string, unknown>[]"
               empty-text="无分红明细">
      <template #dps="{ value }">{{ price(value as number) }}</template>
      <template #payout_ratio="{ value }">{{ pct(value as number) }}</template>
    </DataTable>
  </div>
</template>
