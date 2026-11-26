/**
 * 图表主题：从 CSS 令牌读色值，**不要在 TS 里写死颜色**。
 *
 * 为什么不在 TS 里重复一份色值：`tokens.css` 是唯一真源，双击主题切换时
 * 图表必须跟着变。写死色值的图表在亮色主题下会变成「深色卡片里的暗色线」，
 * 这种 bug 只在切主题时才暴露。
 *
 * 色板顺序来自对标物（经 CVD 相邻对校验），**顺序不可重排**——
 * 重排会让相邻系列在色盲视角下撞色。
 */

/** 12 色图表调色板（顺序固定）。 */
export const CHART_COLORS_DARK = [
  '#f5ae39', '#3fb1ea', '#9c51cc', '#ffb8df', '#4680f1', '#b98749',
  '#b7c9fc', '#e45cbe', '#5ed9e6', '#f67f2f', '#b7a1f5', '#f0d947',
] as const

/** 系列色：按索引取，超过 12 个循环（但同一图内不应超过 12 条线）。 */
export function seriesColor(index: number): string {
  return CHART_COLORS_DARK[index % CHART_COLORS_DARK.length]
}

/** 从 CSS 变量读一个令牌值（含回退）。 */
export function cssVar(name: string, fallback = '#e8e8e8'): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim()
  return value || fallback
}

/** ECharts 基础主题（每次渲染时取当前主题的令牌）。 */
export function baseTheme(): Record<string, unknown> {
  const text = cssVar('--wb-text-secondary', '#b7b7b7')
  const dim = cssVar('--wb-text-tertiary', '#8c8c8c')
  const border = cssVar('--wb-border-dim', '#262626')
  const surface = cssVar('--wb-bg-surface', '#0b0b0b')
  return {
    backgroundColor: 'transparent',
    textStyle: {
      color: text,
      fontFamily: cssVar('--wb-font-mono', 'monospace'),
      fontSize: 12,
    },
    grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: surface,
      borderColor: border,
      textStyle: { color: text, fontSize: 12 },
    },
    legend: { textStyle: { color: dim, fontSize: 11 }, top: 0 },
    xAxis: {
      axisLine: { lineStyle: { color: border } },
      axisLabel: { color: dim, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      axisLine: { lineStyle: { color: border } },
      axisLabel: { color: dim, fontSize: 11 },
      splitLine: { lineStyle: { color: border, type: 'dashed' } },
    },
  }
}

/** A 股涨跌色（红涨绿跌，与西方相反——见 tokens.css）。 */
export function upDownColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return cssVar('--wb-text-tertiary')
  if (value > 0) return cssVar('--wb-up', '#ff5d5d')
  if (value < 0) return cssVar('--wb-down', '#2fd07a')
  return cssVar('--wb-text-secondary')
}

/** K 线实体色：阳线 up / 阴线 down（同一对令牌，供 candlestick 一次性取走）。 */
export function candleColors(): { up: string; down: string } {
  return {
    up: cssVar('--wb-up', '#ff5d5d'),
    down: cssVar('--wb-down', '#2fd07a'),
  }
}

/** 警示色（未知买卖点标记等）。 */
export function warningColor(): string {
  return cssVar('--wb-warning', '#e0a34f')
}
