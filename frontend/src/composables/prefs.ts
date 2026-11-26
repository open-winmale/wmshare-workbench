/**
 * 页面档位/选择的本地持久化（P5-01 轻量版）。
 *
 * **只恢复「选择」，不改变「何时发请求」**：恢复的是输入框与档位；请求
 * 时机仍由各页现有行为决定（有的自动跑、有的点按钮）——持久化不给任何
 * 页面新增一次未经授权的取数。
 *
 * localStorage 异常（隐私模式/被禁用/已满）静默回落默认值——偏好是
 * 锦上添花，不该让页面因此失败。键统一带 `wb.` 前缀，按页命名空间。
 */
export function loadPref<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(`wb.${key}`)
    if (raw === null) {
      return fallback
    }
    const value = JSON.parse(raw) as T
    return value === null || value === undefined ? fallback : value
  } catch {
    return fallback
  }
}

export function savePref(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(`wb.${key}`, JSON.stringify(value))
  } catch {
    /* 存不了就算了：偏好丢失只是回到默认 */
  }
}
