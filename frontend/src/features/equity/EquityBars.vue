<script setup lang="ts">
/**
 * 「行情走势」分区：日 K 线 + 成交量；「分时」分区：当日 1 分钟。
 *
 * 数据契约（后端 `tools/equity/bars.py`）：日 K 已按日期升序、缺 OHLC
 * 的行已被丢掉并在 warnings 里计数；分时 bars 升序 `{t "HH:MM", price}`。
 * 这里**不再过滤**——归一只做一次，前后端各做一遍必然漂移。
 *
 * 「请求 N 根、实际 M 根」要说清楚：`limit` 是最近 N 个交易日，停牌日
 * 天然缺席——把 M < N 说成「缺数据」是错的，把 N 说成 M 也是错的。
 */
import { computed } from 'vue'

import KLineChart, { type Bar } from '../../components/ui/KLineChart.vue'
import LineChart, { type Series } from '../../components/ui/LineChart.vue'
import StateBlock from '../../components/ui/StateBlock.vue'

/** 日 K 行（KLineChart 契约）。 */
export interface BarsData {
  bars?: (Bar | MinutePoint)[]
  count?: number
  days?: number
  first_date?: string
  last_date?: string
  /** 分时分区载荷（mode="minute"） */
  intraday?: boolean
  date?: string
  updated_at?: string
  note?: string
}

/** 分时点：t = "HH:MM"，price = 该分钟收盘（=现价）；avg = 当日均价（自算 VWAP，指数无）。 */
export interface MinutePoint {
  t?: string
  price?: number
  avg?: number
}

const props = defineProps<{ data: BarsData | undefined; mode?: 'daily' | 'minute' }>()

const minute = props.mode === 'minute'
const points = computed<MinutePoint[]>(() =>
  (props.data?.bars ?? []).filter(
    (b): b is MinutePoint => !minute || typeof (b as MinutePoint).t === 'string',
  ),
)
const minuteSeries = computed<Series[]>(() => {
  const price: Series = { name: '分时', data: points.value.map((p) => p.price ?? null) }
  if (!points.value.some((p) => p.avg != null)) return [price]
  return [price, { name: '均价', data: points.value.map((p) => p.avg ?? null) }]
})
const hasAvg = computed(() => minuteSeries.value.length > 1)
const minuteLabels = computed(() => points.value.map((p) => p.t ?? ''))
</script>

<template>
  <template v-if="minute">
    <template v-if="data?.intraday && minuteLabels.length">
      <LineChart :series="minuteSeries" :x-labels="minuteLabels"
                 area :height="300" scale />
      <p class="wb-hint">
        {{ data.date }} 分时，{{ data.count }} 个分钟点，更新于
        {{ data.updated_at || '—' }}（休市时为最近交易日全天分时）<template
          v-if="hasAvg">；均价=当日成交均价（累计额÷累计量自算，指数无）</template>。
      </p>
    </template>
    <StateBlock v-else kind="empty" title="暂无分时数据"
                :detail="data?.note || '未开盘或上游无覆盖。'" />
  </template>
  <template v-else>
    <template v-if="data?.bars?.length">
      <KLineChart :bars="data.bars as Bar[]" :height="380" />
      <p class="wb-hint">
        {{ data.first_date }} → {{ data.last_date }}，共 {{ data.count }} 根
        （请求最近 {{ data.days }} 个交易日；停牌日天然缺席，缺 OHLC 的行不绘制）
      </p>
    </template>
    <StateBlock v-else kind="empty" title="没有日 K 数据"
                detail="可能未上市、已退市或上游无覆盖。" />
  </template>
</template>
