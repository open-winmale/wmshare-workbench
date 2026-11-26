/**
 * 唯一的 fetch 出口（`PROJECT_SPEC` §2 规则 6）。
 *
 * 其它层（components / composables / features）**不得**出现 `fetch(`——
 * 由 `gates/check_layers.py` 强制。这样「网络调用点」只有一个，
 * 错误处理、超时、契约校验都不必在多处重复。
 */

import { ENDPOINTS, type Envelope, type EndpointSlug } from './contract'

/** 统一的请求失败：携带信封里的 action，供 UI 决定显示哪个按钮。 */
export class ApiError extends Error {
  readonly action: string
  readonly code: string
  readonly envelope: Envelope

  constructor(envelope: Envelope) {
    const meta = envelope.meta as { error?: string; code?: string; action?: string }
    super(meta.error ?? '请求失败')
    this.name = 'ApiError'
    this.action = meta.action ?? 'report'
    this.code = meta.code ?? ''
    this.envelope = envelope
  }
}

async function request<T>(
  path: string,
  init: { method: string; body?: unknown; signal?: AbortSignal },
): Promise<Envelope<T>> {
  const resp = await fetch(path, {
    method: init.method,
    headers: init.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  })
  let payload: Envelope<T>
  try {
    payload = (await resp.json()) as Envelope<T>
  } catch {
    throw new Error(`响应不是合法 JSON（HTTP ${resp.status}）`)
  }
  // 业务失败也走 throw，让调用方只处理一种失败形态
  if (payload.ok === false) throw new ApiError(payload)
  return payload
}

/** GET 端点（appinfo / tools / health / assistant）；query 逐键编码。 */
export function get<T>(slug: Extract<EndpointSlug, 'appinfo' | 'tools' | 'health' | 'assistant' | 'assistant_sessions' | 'assistant_stream'>,
                       query?: Record<string, string>,
                       signal?: AbortSignal): Promise<Envelope<T>> {
  const spec = ENDPOINTS[slug]
  const qs = query ? '?' + new URLSearchParams(query).toString() : ''
  return request<T>(spec.path + qs, { method: 'GET', signal })
}

/** POST 工具端点；`slug` 必须是契约里声明过的。 */
export function run<T>(slug: EndpointSlug, body: unknown = {},
                       signal?: AbortSignal): Promise<Envelope<T>> {
  return request<T>(ENDPOINTS[slug].path, { method: 'POST', body, signal })
}
