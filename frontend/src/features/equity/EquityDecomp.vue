<script setup lang="ts">
/**
 * 持有收益拆解分区（高成本）。
 *
 * **它回答的是「这段持有期的收益从哪来」**：总收益 = 价格贡献 + 股息贡献。
 * 股息贡献是后复权与不复权的差值（含再投效应），**不是分红 ÷ 买入价**，
 * 所以标签写「股息贡献」而不写「股息率」——写成股息率会被读成当期收益率。
 *
 * **`ok=false` 是有效结果不是错误**：次新股 K 线覆盖不足时上游只返回
 * `{ok:false, reason}`，没有任何收益字段。这时要显示原因，而不是显示
 * 「加载失败」——后者会让用户去查网络，而问题在于这只票上市太晚。
 */
import { computed } from 'vue'

import BarChart, { type Bar } from '../../components/ui/BarChart.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import LineChart, { type Series } from '../../components/ui/LineChart.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { money, num, pct } from '../../composables/format'

export interface DecompField {
  key: string
  label: string
  value: string | number | null
  format: string
}

export interface YearRow {
  year: string
  price_pct: number | null
  div_pct: number | null
  total_pct: number | null
}

export interface MonthPoint {
  date: string
  cum_price: number | null
  cum_total: number | null
  close_nr: number | null
}

export interface DecompData {
  ok: boolean
  reason?: string
  years: number
  symbol?: string
  span_years?: number | null
  start_date?: string
  end_date?: string
  summary?: DecompField[]
  attribution?: DecompField[]
  yearly?: YearRow[]
  monthly?: MonthPoint[]
}

const props = defineProps<{ data: DecompData | null }>()

/** 汇总四格：总收益 / 价格 / 股息 / 年化。 */
const kpis = computed<Kpi[]>(() => {
  const byKey = new Map((props.data?.summary ?? []).map((f) => [f.key, f]))
  const pick = (key: string): number | null => {
    const v = byKey.get(key)?.value
    return typeof v === 'number' ? v : null
  }
  const total = pick('total_return')
  return [
    { key: 'total', label: '总收益', value: pct(total),
      tone: tone(total) },
    { key: 'price', label: '价格贡献', value: pct(pick('price_return')),
      tone: tone(pick('price_return')) },
    { key: 'div', label: '股息贡献', value: pct(pick('dividend_return')),
      tone: tone(pick('dividend_return')) },
    { key: 'cagr', label: '年化总收益', value: pct(pick('cagr_total')),
      tone: tone(pick('cagr_total')) },
  ]
})

function tone(v: number | null): Kpi['tone'] {
  if (v === null) return 'muted'
  if (v > 0) return 'bad'
  return v < 0 ? 'ok' : 'muted'
}

/** 价格 vs 股息的累计曲线（两条线：拆解的核心是看差距）。 */
const cumSeries = computed<Series[]>(() => {
  const points = props.data?.monthly ?? []
  if (!points.length) return []
  return [
    { name: '累计总收益', data: points.map((p) => p.cum_total) },
    { name: '其中价格', data: points.map((p) => p.cum_price) },
  ]
})
const cumDates = computed(
  () => (props.data?.monthly ?? []).map((p) => p.date),
)

/** 逐年「价格 + 股息」堆叠柱：股息是稳定项，价格是波动项。 */
const yearlyBars = computed<Bar[]>(() =>
  (props.data?.yearly ?? []).map((r) => ({
    label: r.year,
    value: r.price_pct,
  })),
)

const yearColumns: Column[] = [
  { key: 'year', label: '年度', mono: true, dim: true },
  { key: 'price_pct', label: '价格', numeric: true },
  { key: 'div_pct', label: '股息', numeric: true },
  { key: 'total_pct', label: '合计', numeric: true },
]

const summaryColumns: Column[] = [
  { key: 'label', label: '项目' },
  { key: 'value', label: '数值', numeric: true },
]

function cellText(f: DecompField): string {
  if (f.value === null || f.value === undefined) return '—'
  if (f.format === 'pct' && typeof f.value === 'number') return pct(f.value)
  if (f.format === 'money' && typeof f.value === 'number') return money(f.value)
  if (f.format === 'num' && typeof f.value === 'number') return num(f.value)
  return String(f.value)
}
</script>

<template>
  <div>
    <StateBlock v-if="!data" kind="empty" title="无拆解数据"
                hint="重试或换一个标的。" />

    <StateBlock v-else-if="!data.ok" kind="empty"
                :title="`${data.symbol ?? ''} 无法拆解`"
                :detail="data.reason"
                hint="上游算不出不是接口故障：这只票的 K 线覆盖不足（多为次新股），没有足够长的历史可以拆。换更长/更短的年限通常也没用。" />

    <template v-else>
      <p class="meta">
        {{ data.start_date }} → {{ data.end_date }}
        · 实际覆盖 {{ num(data.span_years, 2) }} 年
        · 请求年限 {{ data.years }} 年
      </p>

      <KpiStrip :items="kpis" />

      <div class="grid">
        <div class="wb-card">
          <h2>累计收益拆解</h2>
          <LineChart v-if="cumSeries.length" :series="cumSeries"
                     :x-labels="cumDates" :height="230" />
          <p v-else class="wb-empty">无月末序列</p>
          <p class="note">
            两条线之间即股息贡献（后复权 − 不复权的差值，含再投效应）。
          </p>
        </div>

        <div class="wb-card">
          <h2>逐年价格收益</h2>
          <BarChart :bars="yearlyBars" tone="updown" format="pct"
                    :height="200" />
          <p class="note">股息项见下表；股息通常是稳定正项，价格是波动项。</p>
        </div>
      </div>

      <div class="grid">
        <div class="wb-card">
          <h2>汇总</h2>
          <DataTable :columns="summaryColumns"
                     :rows="(data.summary ?? []) as unknown as Record<string, unknown>[]"
                     empty-text="无汇总">
            <template #value="{ row }">
              {{ cellText(row as unknown as DecompField) }}
            </template>
          </DataTable>
        </div>

        <div class="wb-card">
          <h2>EPS × PE 归因</h2>
          <DataTable v-if="(data.attribution ?? []).length"
                     :columns="summaryColumns"
                     :rows="(data.attribution ?? []) as unknown as Record<string, unknown>[]"
                     empty-text="无归因">
            <template #value="{ row }">
              {{ cellText(row as unknown as DecompField) }}
            </template>
          </DataTable>
          <p v-else class="wb-empty">上游未给出归因</p>
        </div>
      </div>

      <h2 class="wb-h2">逐年明细（{{ (data.yearly ?? []).length }} 年）</h2>
      <DataTable :columns="yearColumns"
                 :rows="(data.yearly ?? []) as unknown as Record<string, unknown>[]"
                 empty-text="无逐年数据">
        <template #price_pct="{ value }">{{ pct(value as number) }}</template>
        <template #div_pct="{ value }">{{ pct(value as number) }}</template>
        <template #total_pct="{ value }">{{ pct(value as number) }}</template>
      </DataTable>
    </template>
  </div>
</template>

<style scoped>
.meta {
  margin: 0 0 var(--wb-sp-4);
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--wb-sp-5);
}

h2 {
  margin: 0 0 var(--wb-sp-4);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.note {
  margin: var(--wb-sp-3) 0 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
  line-height: 1.6;
}
</style>
