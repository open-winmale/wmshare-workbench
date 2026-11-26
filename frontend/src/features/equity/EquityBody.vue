<script setup lang="ts">
/**
 * 个股研究的内容区：把「当前分区 → 该渲染哪个视图」这一段收在一处。
 *
 * **拆出来的理由**：`EquityView` 的职责是「壳 + 取数编排」（标的输入、
 * 页签、确认流程）；它一旦还要认识每个分区的数据形状，就会随着分区增加
 * 一直长下去。这里只做分发，不碰取数。
 *
 * 每个分区的数据都从 `data.data` 下**扁平键**读（不是嵌套一层分区名）：
 * 早期版本在分红分区套了一层 `dividend`，props 恒为空，页面静默显示
 * 「—」——数据明明取到了，只是读错了位置。
 */
import LineChart, { type Series } from '../../components/ui/LineChart.vue'
import type { Bar } from '../../components/ui/KLineChart.vue'
import EquityBars, { type BarsData } from './EquityBars.vue'
import EquityDecomp, { type DecompData } from './EquityDecomp.vue'
import EquityDividend, {
  type DividendField,
  type DividendRow,
} from './EquityDividend.vue'
import EquityForecast, { type ForecastBlock } from './EquityForecast.vue'
import EquityOverview, { type DividendBrief } from './EquityOverview.vue'
import EquityStatements, { type StatementRow } from './EquityStatements.vue'

export interface Snapshot {
  name?: string
  industry?: string
  close?: number
  percent?: number
  chg_20d?: number
  roi_1y?: number
  ma20?: number
  ma60?: number
  mv?: number
  vol_ratio_5?: number
  kline_date?: string
  is_st?: boolean
  is_suspend?: boolean
}

/** 分区的载荷（键随分区而变，全部扁平）。 */
export interface SectionData {
  snapshot?: Snapshot
  dividend?: DividendBrief
  bars?: Bar[]
  count?: number
  days?: number
  first_date?: string
  last_date?: string
  series?: Record<string, { date: string; value: number }[]>
  fields?: string[]
  periods?: string[]
  period?: 'annual' | 'quarter'
  rows?: StatementRow[]
  dividend_fields?: DividendField[]
  dividend_history?: DividendRow[]
  forecast_blocks?: ForecastBlock[]
  yjyg_age_days?: number | null
  yjyg_stale?: boolean
}

const props = defineProps<{
  symbol: string
  section: string
  data: SectionData | undefined
  /** 拆解分区专用：它的载荷结构与其它分区不同 */
  decomp: DecompData | null
  domain: 'indicators' | 'income' | 'balance' | 'cashflow'
  /** 报表期档（年报/季报），三表与指标共用 */
  stmtPeriod?: 'annual' | 'quarter'
}>()

const emit = defineEmits<{
  pickStatement: [kind: 'indicators' | 'income' | 'balance' | 'cashflow']
  setPeriod: [period: 'annual' | 'quarter']
}>()

/** 估值序列：PE / PB / PS 三条线（有哪条画哪条）。 */
function peSeries(data: SectionData | undefined): Series[] {
  const series = data?.series ?? {}
  return ['pe_ttm', 'pb', 'ps']
    .filter((k) => series[k]?.length)
    .map((k) => ({ name: k, data: series[k].map((p) => p.value) }))
}

function peDates(data: SectionData | undefined): string[] {
  const series = data?.series ?? {}
  const first = series.pe_ttm ?? series.pb ?? series.ps ?? []
  return first.map((p) => p.date)
}
</script>

<template>
  <EquityOverview v-if="section === 'overview'" :symbol="symbol"
                  :snapshot="data?.snapshot ?? {}"
                  :dividend="(data?.dividend ?? {}) as DividendBrief" />

  <!-- 行情走势在概览之后、估值之前：先看价格怎么走，再看贵不贵 -->
  <EquityBars v-else-if="section === 'bars'" :data="(data ?? {}) as BarsData" />

  <!-- 分时：当日 1 分钟（盘中实时；独立分区=用户点击才发，~1.6k EC/次） -->
  <EquityBars v-else-if="section === 'minute'" mode="minute"
              :data="(data ?? {}) as BarsData" />

  <template v-else-if="section === 'valuation'">
    <h2 class="wb-h2">估值序列（{{ data?.fields?.length ?? 0 }} 个字段）</h2>
    <LineChart v-if="peSeries(data).length" :series="peSeries(data)"
               :x-labels="peDates(data)" :height="260" />
    <p v-else class="wb-empty">无估值序列</p>
  </template>

  <EquityStatements v-else-if="section === 'statements'"
                    :periods="data?.periods ?? []"
                    :rows="data?.rows ?? []"
                    :kind="domain" :period="stmtPeriod ?? 'annual'"
                    @pick="emit('pickStatement', $event)"
                    @set-period="emit('setPeriod', $event)" />

  <EquityDividend v-else-if="section === 'dividend'"
                  :fields="data?.dividend_fields ?? []"
                  :history="data?.dividend_history ?? []" />

  <EquityForecast v-else-if="section === 'forecast'"
                  :blocks="data?.forecast_blocks ?? []"
                  :age-days="data?.yjyg_age_days ?? null"
                  :stale="data?.yjyg_stale === true" />

  <EquityDecomp v-else-if="section === 'decomp'" :data="props.decomp" />

  <template v-else>
    <h2 class="wb-h2">{{ section }}</h2>
    <pre class="raw">{{ JSON.stringify(data, null, 2) }}</pre>
  </template>
</template>
