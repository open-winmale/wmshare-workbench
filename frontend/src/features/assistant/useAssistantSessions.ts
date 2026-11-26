/**
 * 助手会话生命周期（store 侧）。
 */
import { ref } from 'vue'

import { get, run } from '../../api/client'
import type { SessionMeta } from './types'

export function useAssistantSessions() {
  const sessions = ref<SessionMeta[]>([])

  async function reload(): Promise<void> {
    try {
      const env = await get<{ sessions: SessionMeta[] }>('assistant_sessions')
      sessions.value = env.data.sessions ?? []
    } catch {
      sessions.value = []
    }
  }

  async function open(id: string): Promise<ChatFetch | null> {
    const env = await run<{ id: string; title: string; messages: unknown[] }>(
      'assistant_session', { id })
    return { id, title: env.data.title, messages: env.data.messages }
  }

  async function remove(id: string): Promise<boolean> {
    const env = await run<{ deleted: boolean }>('assistant_session',
                                                { id, action: 'delete' })
    await reload()
    return env.data.deleted
  }

  return { sessions, reload, open, remove }
}

export interface ChatFetch {
  id: string
  title: string
  messages: unknown[]
}
