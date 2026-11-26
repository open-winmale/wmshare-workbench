<script setup lang="ts">
/**
 * K 线图：蜡烛 + 成交量副图 + 可选买卖点标记（工作台第 3 类图表，D-16）。
 *
 * 每一类图表都要守的三条（`DEBT.md` D-16 的处置方案原文）：
 * 1. **双主题**：色值全部来自 CSS 令牌——红涨绿跌是 A 股口径
 *    （`--wb-up`/`--wb-down`）；主题切换经 `themeState` 触发重渲染。
 * 2. **null 不补 0**：缺 OHLC 的日子整根不画（后端 `normalize_bars`
 *    已丢掉并计数）；`volume` 为 null 时量柱缺席，不掉到 0——掉到 0
 *    会把「停牌/缺数」画成「缩量到零」，那是编造事实。
 * 3. **无硬编码色值**：兜底色只存在于 `cssVar()` 的 fallback 参数里。
 *
 * 标记 `side` 只把 `buy`/`sell` 画成红三角/绿三角；**其它值画成中性
 * 菱形**——上游换了枚举时标记「莫名变少」比「长了个菱形」更糟，
 * 落在 K 线区间外的标记计数显示，不静默丢弃。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

import { baseTheme, candleColors, warningColor } from '../../styles/chart-theme'
import { cvdOn, themeName } from '../../styles/themeState'

echarts.use([CandlestickChart, BarChart, ScatterChart, GridComponent,
  TooltipComponent, CanvasRenderer])

export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
  amount?: number | null
  percent?: number | null
}

export interface Mark {
  date: string
  price: number | null
  /** 买/卖；其它值渲染为中性标记（不丢弃） */
  side: string
}

const props = withDefaults(defineProps<{
  /** 已按日期升序（后端 `normalize_bars` 保证，这里不重复归一） */
  bars: Bar[]
  marks?: Mark[]
  height?: number
}>(), { marks: () => [], height: 360 })

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

/** 日期 → 序号（x 轴是类别轴；区间外的标记按它识别出来）。 */
const dateIndex = computed(() => {
  const map = new Map<string, number>()
  props.bars.forEach((b, i) => map.set(b.date, i))
  return map
})

const unmatched = computed(() =>
  props.marks.filter((m) => !dateIndex.value.has(m.date)).length)

function fmtVol(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(1)} 万`
  return String(Math.round(v))
}

/** 悬停提示：开收高低 + 量 + 涨跌 + 当日买卖点（数值直接取 bars，
 * 不从 ECharts 参数里抠——标记系列会混进 params）。 */
function tip(params: unknown): string {
  const list = Array.isArray(params) ? params : [params]
  const first = list[0] as { dataIndex?: number } | undefined
  const b = props.bars[first?.dataIndex ?? -1]
  if (!b) return ''
  const rows = [`<b>${b.date}</b>`,
    `开 ${b.open}　收 ${b.close}　高 ${b.high}　低 ${b.low}`]
  if (b.volume !== null && b.volume !== undefined) rows.push(`量 ${fmtVol(b.volume)}`)
  if (b.percent !== null && b.percent !== undefined) {
    rows.push(`涨跌 ${(b.percent * 100).toFixed(2)}%`)
  }
  const dayMarks = props.marks.filter((m) => m.date === b.date)
  if (dayMarks.length) {
    rows.push(dayMarks.map((m) => {
      const label = m.side === 'buy' ? '买入'
        : m.side === 'sell' ? '卖出' : `标记(${m.side})`
      return `${label} @ ${m.price}`
    }).join('　'))
  }
  return rows.join('<br/>')
}

const option = computed(() => {
  // 色值经 getComputedStyle 在渲染时读取——非响应式，必须把主题状态显式
  // 挂进依赖图，切主题/色盲变体时本 computed 才会重算（只 watch 不重算
  // 是不够的：会把缓存里的旧色重画一遍，指纹实测抓到过这个洞）
  void [themeName.value, cvdOn.value]
  const theme = baseTheme() as Record<string, unknown>
  const axisTheme = theme.xAxis as { axisLabel?: Record<string, unknown> }
  const { up, down } = candleColors()
  const neutral = warningColor()
  const marks = props.marks.flatMap((m) => {
    const idx = dateIndex.value.get(m.date)
    if (idx === undefined || m.price === null || m.price === undefined) return []
    const kind = m.side === 'buy' ? 'buy'
      : m.side === 'sell' ? 'sell' : 'other'
    const color = kind === 'buy' ? up : kind === 'sell' ? down : neutral
    return [{
      value: [idx, m.price],
      symbol: kind === 'other' ? 'diamond' : 'triangle',
      symbolRotate: kind === 'sell' ? 180 : 0,
      symbolSize: kind === 'other' ? 10 : 9,
      itemStyle: { color },
    }]
  })
  const dates = props.bars.map((b) => b.date)
  const series: Record<string, unknown>[] = [{
    name: 'K线', type: 'candlestick', data: props.bars.map((b) =>
      [b.open, b.close, b.low, b.high]),
    xAxisIndex: 0, yAxisIndex: 0,
    itemStyle: { color: up, color0: down, borderColor: up, borderColor0: down },
  }]
  if (marks.length) {
    series.push({ name: '买卖点', type: 'scatter', xAxisIndex: 0,
      yAxisIndex: 0, data: marks, z: 10 })
  }
  series.push({
    name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
    data: props.bars.map((b) => ({
      value: b.volume ?? null,
      itemStyle: { color: b.close >= b.open ? up : down, opacity: 0.7 },
    })),
  })
  return {
    ...theme,
    animation: false,
    tooltip: { ...(theme.tooltip as object), trigger: 'axis', formatter: tip },
    legend: { ...(theme.legend as object),
      data: marks.length ? ['K线', '买卖点', '成交量'] : ['K线', '成交量'] },
    grid: [
      { left: 8, right: 12, top: 30, height: '56%', containLabel: true },
      { left: 8, right: 12, top: '74%', bottom: 8, containLabel: true },
    ],
    xAxis: [
      { ...(theme.xAxis as object), type: 'category', data: dates,
        boundaryGap: true,
        axisLabel: { ...axisTheme.axisLabel, show: false } },
      { ...(theme.xAxis as object), type: 'category', gridIndex: 1,
        data: dates, boundaryGap: true },
    ],
    yAxis: [
      { ...(theme.yAxis as object), type: 'value', scale: true },
      { ...(theme.yAxis as object), type: 'value', gridIndex: 1,
        axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series,
  }
})

function render(): void {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(option.value, true)
}

function resize(): void {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(option, render)
</script>

<template>
  <div class="chart">
    <div ref="el" class="canvas" :style="{ height: `${height}px` }" />
    <p v-if="bars.length === 0" class="empty">无 K 线数据</p>
    <p v-if="unmatched" class="note">
      {{ unmatched }} 个买卖点不在当前 K 线区间内，未上图（成交明细表里仍完整）
    </p>
  </div>
</template>

<style scoped>
.chart {
  position: relative;
  width: 100%;
}

.canvas {
  width: 100%;
}

.empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.note {
  margin: 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}
</style>
