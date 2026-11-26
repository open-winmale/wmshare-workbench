/**
 * 工具页的统一取数生命周期。
 *
 * 三个坑由它统一处理（每个页面各写一遍必然会有一个写漏）：
 *
 * 1. **组件卸载后响应到达**：不 guard 的话 `data.value = ...` 会往已销毁
 *    的组件写状态，切换页面很快时必然出现。用 `AbortController` + 序号双保险。
 * 2. **慢响应覆盖快响应**：用户快速切两次标的，先发的请求可能后回来。
 *    用递增序号丢弃过期响应（"最后一次请求才是当前请求"）。
 * 3. **错误态与数据的互斥**：出错时必须清掉旧数据，否则页面上会同时
 *    显示「加载失败」和上一次的表格，用户不知道哪个是真的。
 */

import { onBeforeUnmount, ref, shallowRef } from 'vue'

import { ApiError, run } from '../api/client'
import type { EndpointSlug } from '../api/contract'

export interface LoadError {
  message: string
  /** 处置动作（retry / topup / config / fix_input / report） */
  action: string
  code: string
}

export function useTool<T>(slug: EndpointSlug) {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const error = ref<LoadError | null>(null)
  const asOf = ref('')
  const warnings = ref<string[]>([])

  let seq = 0
  let controller: AbortController | null = null

  /** 发起一次请求；同名重复调用只保留最后一次。 */
  async function load(params: unknown = {}): Promise<void> {
    seq += 1
    const mine = seq
    controller?.abort()
    controller = new AbortController()

    loading.value = true
    error.value = null
    try {
      const env = await run<T>(slug, params, controller.signal)
      if (mine !== seq) return          // 已有更新的请求，丢弃这次
      data.value = env.data
      asOf.value = env.as_of
      warnings.value = env.warnings ?? []
    } catch (exc) {
      if (mine !== seq) return
      if (exc instanceof DOMException && exc.name === 'AbortError') return
      // 出错必须清数据：同时显示「失败」与上一次结果会让人分不清真假
      data.value = null
      error.value = toError(exc)
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  onBeforeUnmount(() => {
    controller?.abort()
    controller = null
  })

  return { data, loading, error, asOf, warnings, load }
}

function toError(exc: unknown): LoadError {
  if (exc instanceof ApiError) {
    return { message: exc.message, action: exc.action, code: exc.code }
  }
  return {
    message: exc instanceof Error ? exc.message : String(exc),
    action: 'report',
    code: '',
  }
}

/** 处置动作 → 中文按钮文案。 */
export const ACTION_LABEL: Record<string, string> = {
  retry: '重试',
  topup: '去充值',
  config: '去配置',
  fix_input: '修改输入',
  report: '报告问题',
}
