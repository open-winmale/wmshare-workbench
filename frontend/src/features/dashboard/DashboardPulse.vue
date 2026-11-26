<script setup lang="ts">
/**
 * 今日盘面 · 涨跌分布直方图 + 涨幅/跌幅榜。
 *
 * bins 是**分桶计数**（全为正数）——柱色不能按数值正负（会全红），
 * 桶的涨跌语义在 label 里：负区间（`-3~0`）与「跌停」绿、「平盘」灰、
 * 其余红。上游无日期字段，数据日由页头「最新交易日」chip 承担。
 */
import BarChart from '../../components/ui/BarChart.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import { candleColors, cssVar } from '../../styles/chart-theme'
import { pct, trendClass } from '../../composables/format'

export interface Bin {
  label: string
  count?: number | null
}

export interface Mover {
  symbol?: string
  name?: string
  percent?: number | null
}

export interface PulseData {
  bins?: Bin[]
  gainers?: Mover[]
  losers?: Mover[]
}

defineProps<{ dist: PulseData }>()

/** 桶 label → 涨跌色（计数全正，语义在 label；色值经主题令牌解析，
 * .vue 里不写裸色值）。 */
function binColor(label: string): string {
  const { up, down } = candleColors()
  const isDown = label.startsWith('-') || label.includes('跌停')
  if (isDown) return down
  if (label === '平盘' || label.includes('平')) {
    return cssVar('--wb-text-secondary')
  }
  return up
}

const barColor = (b: Bin) => binColor(b.label)

const moverColumns: Column[] = [
  { key: 'name', label: '名称' },
  { key: 'percent', label: '涨跌幅', numeric: true },
]

function asRows(rows: Mover[] | undefined): Record<string, unknown>[] {
  return (rows ?? []) as unknown as Record<string, unknown>[]
}
</script>

<template>
  <div class="pulse">
    <div class="wb-card">
      <h2 class="card-head">涨跌分布</h2>
      <BarChart v-if="(dist.bins ?? []).length"
                :bars="(dist.bins ?? []).map((b) => ({ label: b.label,
                                                      value: b.count ?? null }))"
                :color-of="barColor" :height="180" />
      <p v-else class="empty">无分布数据</p>
    </div>

    <div class="wb-card">
      <h2 class="card-head">涨幅榜</h2>
      <DataTable :columns="moverColumns" :rows="asRows(dist.gainers)"
                 empty-text="无涨幅榜数据">
        <template #name="{ row }">
          {{ (row as unknown as Mover).name ?? (row as unknown as Mover).symbol }}
        </template>
        <template #percent="{ value }">
          <span :class="trendClass(value as number)">{{ pct(value as number) }}</span>
        </template>
      </DataTable>
    </div>

    <div class="wb-card">
      <h2 class="card-head">跌幅榜</h2>
      <DataTable :columns="moverColumns" :rows="asRows(dist.losers)"
                 empty-text="无跌幅榜数据">
        <template #name="{ row }">
          {{ (row as unknown as Mover).name ?? (row as unknown as Mover).symbol }}
        </template>
        <template #percent="{ value }">
          <span :class="trendClass(value as number)">{{ pct(value as number) }}</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<style scoped>
.pulse {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: var(--wb-sp-4);
  padding: var(--wb-sp-4) var(--wb-sp-6) var(--wb-sp-6);
}

@media (max-width: 1000px) {
  .pulse {
    grid-template-columns: 1fr;
  }
}

.card-head {
  margin: 0 0 var(--wb-sp-3);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.empty {
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}
</style>
