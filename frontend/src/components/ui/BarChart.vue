<script setup lang="ts">
/**
 * 柱状图：分类柱 + 可选涨跌着色。
 *
 * `tone="updown"` 时柱子按数值正负着色（A 股红涨绿跌）。这是行情类
 * 图表最常被误做成「统一蓝色」的地方——统一色让用户必须去读数字才能
 * 知道涨还是跌，而柱子的高度本来就已经表达了幅度。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

import { baseTheme, seriesColor, upDownColor } from '../../styles/chart-theme'
import { cvdOn, themeName } from '../../styles/themeState'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

export interface Bar {
  label: string
  value: number | null
}

const props = withDefaults(defineProps<{
  bars: Bar[]
  height?: number
  /** `updown` = 按正负着色；`series` = 统一系列色 */
  tone?: 'updown' | 'series'
  format?: 'num' | 'pct' | 'money'
  /** 是否横向条形（分类名较长时更好读） */
  horizontal?: boolean
  /**
   * 逐柱自定义色（涨跌分布直方图用：计数值全为正，「按数值正负」
   * 会全红——桶的涨跌语义在 label 里，由调用方按 label 给色）。
   * 给了它就盖过 tone。
   */
  colorOf?: (bar: Bar, index: number) => string | undefined
}>(), { height: 220, tone: 'series', format: 'num', horizontal: false })

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function fmt(value: number): string {
  if (props.format === 'pct') return `${(value * 100).toFixed(2)}%`
  if (props.format === 'money') {
    if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`
    if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(1)} 万`
  }
  return String(value)
}

const option = computed(() => {
  // 色值经 getComputedStyle 在渲染时读取——非响应式，必须把主题状态显式
  // 挂进依赖图，切主题/色盲变体时本 computed 才会重算
  void [themeName.value, cvdOn.value]
  const theme = baseTheme() as Record<string, unknown>
  const labels = props.bars.map((b) => b.label)
  const data = props.bars.map((b, i) => {
    if (b.value === null) return null
    const custom = props.colorOf?.(b, i)
    const color = custom
      ?? (props.tone === 'updown' ? upDownColor(b.value) : seriesColor(i))
    return { value: b.value, itemStyle: { color } }
  })
  const category = {
    type: 'category',
    data: labels,
    axisLabel: { color: undefined, fontSize: 11, interval: 0 },
  }
  const value = {
    type: 'value',
    axisLabel: { formatter: (v: number) => fmt(v), fontSize: 11 },
  }
  return {
    ...theme,
    animation: false,
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      ...(theme.tooltip as object),
      valueFormatter: (v: number | null) =>
        v === null || v === undefined ? '缺失' : fmt(v),
    },
    xAxis: props.horizontal ? value : category,
    yAxis: props.horizontal ? { ...category, inverse: true } : value,
    series: [{ type: 'bar', data, barMaxWidth: 24 }],
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
    <p v-if="bars.length === 0" class="empty">无数据可绘制</p>
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
