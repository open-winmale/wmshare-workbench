/**
 * 助手的前端类型（对齐 `tools/assistant/handler.py` 信封载荷）。
 */

export interface SourceItem {
  n: number
  kind: string
  title: string
  detail: string
  as_of: string
}

export interface StepItem {
  tool?: string
  brief?: string
}

/** `GET /api/assistant/stream` 的任务快照（轮询的就是它）。 */
export interface StreamSnapshot {
  job_id: string
  session_id: string
  status: 'running' | 'done' | 'error' | 'stopped'
  phase: string
  steps: StepItem[]
  text: string
  sources: SourceItem[]
  error: { message: string; code: string; action: string } | null
  title: string
}

/** 本地聊天消息（历史来自 store，直播来自快照）。 */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
}

/** `GET /api/assistant/info`：先看状态再发问。 */
export interface AssistantInfo {
  assistant: {
    configured: boolean
    base_host: string
    model: string
    key_tail: string
    max_ec: number
  }
  auth_mode: string
  mode_reason: string
  domains: DomainInfo[]
  max_ec: number
}

export interface DomainInfo {
  id: string
  display_name: string
  description: string
  when_to_use: string
  tools: string[]
}

export interface SessionMeta {
  id: string
  title: string
  created_at: string
  updated_at: string
}
