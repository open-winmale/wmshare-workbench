<script setup lang="ts">
/**
 * 折线图：单/多系列，可选面积填充。
 *
 * **为什么不用 ECharts 的默认样式**：默认主题是浅色背景 + 蓝色系，
 * 放进暗色工作台里会像嵌入了一个别人的网页。主题从 CSS 令牌读
 * （`chart-theme.ts`），切主题时图表跟着变。
 *
 * **数据缺失用 `null` 不补 0**：折线在缺失处断开，而不是掉到 0。
 * 掉到 0 会让「数据缺失」看起来像「数值暴跌」。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

import { baseTheme, seriesColor } from '../../styles/chart-theme'
import { cvdOn, themeName } from '../../styles/themeState'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent,
  CanvasRenderer])

export interface Series {
  name: string
  /** 数据点；`null` 表示该点缺失（线上断开，不补 0） */
  data: (number | null)[]
}

const props = withDefaults(defineProps<{
  series: Series[]
  xLabels: string[]
  height?: number
  /** 是否面积填充（单系列时观感更好） */
  area?: boolean
  /** y 轴格式化：`pct` = 小数转百分比 */
  format?: 'num' | 'pct' | 'money'
  /**
   * y 轴脱离 0 值比例（贴数据域）。默认 false（含 0）——估值曲线等
   * 「0 是有意义参照」的图保持现状；分时这类「只看日内波动」的图必须
   * 开，否则 3900 点的指数线贴顶画成一条平线，±1% 的波动不可见。
   */
  scale?: boolean
  /**
   * 裸模式（指数卡 mini 图用）：隐藏双轴与提示，四边贴边，只留一条线。
   * winmale 式 sparkline——走势形状就是全部信息，轴反而是噪音。
   */
  bare?: boolean
}>(), { height: 220, area: false, format: 'num' })

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function fmt(value: number): string {
  if (props.format === 'pct') return `${(value * 100).toFixed(2)}%`
  if (props.format === 'money') {
    if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`
    if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(1)} 万`
  }
  return String(Math.round(value * 100) / 100)
}

const option = computed(() => {
  // 色值经 getComputedStyle 在渲染时读取——非响应式，必须把主题状态显式
  // 挂进依赖图，切主题/色盲变体时本 computed 才会重算
  void [themeName.value, cvdOn.value]
  const theme = baseTheme() as Record<string, unknown>
  return {
    ...theme,
    animation: false,
    tooltip: props.bare ? { show: false } : {
      ...(theme.tooltip as object),
      valueFormatter: (v: number | null) =>
        v === null || v === undefined ? '缺失' : fmt(v),
    },
    legend: props.bare ? { show: false } : undefined,
    grid: props.bare
      ? { top: 2, left: 2, right: 2, bottom: 2, containLabel: false }
      : undefined,
    xAxis: props.bare
      ? { type: 'category', data: props.xLabels, boundaryGap: false, show: false }
      : {
          ...(theme.xAxis as object),
          type: 'category',
          data: props.xLabels,
          boundaryGap: false,
        },
    yAxis: props.bare
      ? { type: 'value', scale: true, show: false }
      : {
          ...(theme.yAxis as object),
          type: 'value',
          scale: props.scale === true,
          axisLabel: { formatter: (v: number) => fmt(v), fontSize: 11 },
        },
    series: props.series.map((s, i) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      showSymbol: false,
      smooth: false,
      connectNulls: false,
      lineStyle: { width: 1.6, color: seriesColor(i) },
      itemStyle: { color: seriesColor(i) },
      areaStyle: props.area
        ? { opacity: 0.12, color: seriesColor(i) }
        : undefined,
    })),
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
    <p v-if="series.length === 0" class="empty">无数据可绘制</p>
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
</style>
