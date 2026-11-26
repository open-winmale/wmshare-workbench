/** 纯格式化函数（与 Vue 无关，可单测）。 */

export function stateLabel(f: string): string {
  return (
    { fresh: '正常', stale: '预警', expired: '已过期', unknown: '未知' }[f] ?? f
  )
}

/** TTL 人的可读化：604800s → 「1 周」。 */
export function formatTtl(seconds: number): string {
  if (seconds >= 604800) return `${Math.round(seconds / 604800)} 周`
  if (seconds >= 86400) return `${Math.round(seconds / 86400)} 天`
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} 小时`
  return `${seconds} 秒`
}
