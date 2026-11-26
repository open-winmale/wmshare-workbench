/**
 * 数值格式化（**所有页面共用一份**）。
 *
 * 单位与小数位在这里统一，不在各页面各写一遍——否则会出现「行情页显示
 * 1.75%，自选页显示 1.8%」这种同一份数据两种精度的问题，而用户会以为
 * 其中一个算错了。
 *
 * A 股口径（`docs/REPLACE` → wmshare 契约）：涨跌幅/占比=**小数**，
 * 金额=元，量=股。所以 `0.0175` 要显示成 `+1.75%`。
 */

/** 小数 → 百分比字符串（`0.0175` → `+1.75%`）。 */
export function pct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(digits)}%`
}

/** 金额：元 → 亿/万（带符号）。 */
export function money(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(digits)} 万亿`
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(digits)} 亿`
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(digits)} 万`
  return `${sign}${abs.toFixed(0)}`
}

/** 数量（股/手）：整数带千分位。 */
export function qty(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return Math.round(value).toLocaleString('zh-CN')
}

/** 价格：两位小数。 */
export function price(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

/** 普通数字（带千分位）。 */
export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 涨跌方向 → CSS class（`up` / `down` / `flat`）。 */
export function trendClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'flat'
  }
  if (value > 0) return 'up'
  if (value < 0) return 'down'
  return 'flat'
}

/** 按 `format` 字段格式化（后端在 `summary_labels` 里声明口径）。 */
export function byFormat(value: unknown, format: string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (format === 'pct') return pct(value)
  if (format === 'money') return money(value)
  if (format === 'int') return String(Math.round(value))
  return num(value)
}

/** 今日（YYYY-MM-DD，本地时区的 ISO 截断）。 */
export function today(): string {
  return new Date().toISOString().slice(0, 10)
}

/** 今天偏移 N 年的日期（回测默认「近两年」这类滚动窗）。 */
export function shiftYears(delta: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() + delta)
  return d.toISOString().slice(0, 10)
}
