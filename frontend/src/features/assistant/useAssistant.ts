/**
 * 助手对话内核：send → chat 起任务 → 轮询 stream → 落定一条消息。
 *
 * 状态建模刻意简单（本地单用户）：消息就是数组，直播中的一轮是
 * 一个 `live` 快照（阶段胶囊 + 已流出文本 + 来源账），落定时并入
 * `messages`。没有多设备、没有乐观去重——那些机制本地用不上。
 */
import { computed, onBeforeUnmount, ref } from 'vue'

import { ApiError, get, run } from '../../api/client'
import type { AssistantInfo, ChatMessage, StreamSnapshot } from './types'

const POLL_MS = 800

export function useAssistant() {
  const sessionId = ref('')
  const messages = ref<ChatMessage[]>([])
  const live = ref<StreamSnapshot | null>(null)
  const sending = ref(false)
  const turnError = ref<{ message: string; action: string } | null>(null)

  const running = computed(() => live.value?.status === 'running')
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let currentJob = ''

  /** 发起一轮提问。落定后消息进 `messages`；错误进 `turnError`。 */
  async function send(text: string): Promise<void> {
    const content = text.trim()
    if (!content || sending.value) return
    turnError.value = null
    sending.value = true
    messages.value = [...messages.value, { role: 'user', content }]
    try {
      const body: Record<string, unknown> = { message: content }
      if (sessionId.value) body.session_id = sessionId.value
      const env = await run<{ job_id: string; session_id: string }>(
        'assistant_chat', body)
      sessionId.value = env.data.session_id
      currentJob = env.data.job_id
      live.value = blankSnapshot(env.data.job_id, env.data.session_id)
      await poll()
    } catch (exc) {
      turnError.value = toTurnError(exc)
      sending.value = false
    }
  }

  async function stop(): Promise<void> {
    if (!currentJob) return
    await run('assistant_stop', { job_id: currentJob })
  }

  function poll(): Promise<void> {
    return new Promise((resolve) => {
      pollTimer = setTimeout(async () => {
        try {
          const env = await get<StreamSnapshot>('assistant_stream',
                                                { job_id: currentJob })
          live.value = env.data
        } catch {
          live.value = null
          sending.value = false
          return resolve()
        }
        if (live.value && live.value.status === 'running') return resolve(poll())
        settle()
        resolve()
      }, POLL_MS)
    })
  }

  function settle(): void {
    const snap = live.value
    sending.value = false
    if (!snap) return
    if (snap.status === 'error') {
      turnError.value = { message: snap.error?.message ?? '本轮失败',
                          action: snap.error?.action ?? 'retry' }
    } else if (snap.status === 'stopped') {
      messages.value = [...messages.value,
                        { role: 'assistant', content: snap.text || '（已停止）' }]
    } else {
      messages.value = [...messages.value, {
        role: 'assistant', content: snap.text, sources: snap.sources,
      }]
    }
    live.value = null
  }

  function blankSnapshot(jobId: string, sid: string): StreamSnapshot {
    return { job_id: jobId, session_id: sid, status: 'running', phase: '在读上下文',
             steps: [], text: '', sources: [], error: null,
             title: '' }
  }

  function newChat(): void {
    sessionId.value = ''
    messages.value = []
    live.value = null
    turnError.value = null
  }

  onBeforeUnmount(() => {
    if (pollTimer) clearTimeout(pollTimer)
  })

  return { sessionId, messages, live, sending, running, turnError,
           send, stop, newChat }
}

/** 助手配置状态（引导卡与域提示）。放本文件保持「助手取数」在一处。 */
export async function fetchAssistantInfo(): Promise<AssistantInfo> {
  const env = await get<AssistantInfo>('assistant')
  return env.data
}

function toTurnError(exc: unknown): { message: string; action: string } {
  if (exc instanceof ApiError) {
    return { message: exc.message, action: exc.action }
  }
  return { message: exc instanceof Error ? exc.message : String(exc),
           action: 'retry' }
}
