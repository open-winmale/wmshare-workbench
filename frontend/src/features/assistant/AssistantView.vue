<script setup lang="ts">
/**
 * AI 助手页：会话侧栏 + 消息流 + 输入条。
 *
 * 先看状态再发问：未接入数据源 / 未配模型时给引导卡（对应 chat 端点的
 * 两道门），而不是发问后被挡回来。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import {
  fetchAssistantInfo,
  useAssistant,
} from './useAssistant'
import { useAssistantSessions } from './useAssistantSessions'
import type { AssistantInfo, ChatMessage, SessionMeta } from './types'
import AssistantComposer from './AssistantComposer.vue'
import AssistantMessage from './AssistantMessage.vue'

const { sessionId, messages, live, sending, running, turnError,
        send: doSend, stop, newChat } = useAssistant()
const { sessions, reload, open, remove: removeSession } = useAssistantSessions()

const info = ref<AssistantInfo | null>(null)
const activeId = ref('')

const ready = computed(() => {
  if (!info.value) return false
  if (info.value.auth_mode === 'missing') return false
  return info.value.assistant.configured
})

const PROMPTS = [
  '600519 现在多少钱？今天涨跌如何？',
  '今天市场整体涨跌分布怎么样？',
  '贵州茅台最近一年的分红情况怎么样？',
  '$CPI 最新一期是多少？趋势如何？',
  '我的自选清单里有哪些标的？',
]

onMounted(async () => {
  try {
    info.value = await fetchAssistantInfo()
  } catch {
    info.value = null
  }
  await reload()
})

function pick(id: string): void {
  activeId.value = id
  newChat()
  open(id).then((fetch_) => {
    if (!fetch_) return
    sessionId.value = id
    messages.value = fetch_.messages as ChatMessage[]
  })
}

function freshChat(): void {
  activeId.value = ''
  newChat()
}

async function remove(id: string): Promise<void> {
  await removeSession(id)
  if (activeId.value === id) freshChat()
}

function send(text: string): void {
  doSend(text).then(() => reload())
}

const scroller = ref<HTMLElement | null>(null)
function stickBottom(): void {
  void nextTick().then(() => {
    const el = scroller.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
// 快照每次轮询整体替换：直播文本增长与落定都靠它触发贴底
watch(live, stickBottom)
watch(messages, stickBottom)

function titleOf(session: SessionMeta): string {
  return session.title || session.id
}
</script>

<template>
  <PanelShell title="助手"
              subtitle="AI 数据问答：先查目录再取数，每个数字带来源与口径（不构成投资建议）"
              :as-of="''" :loading="false">
    <div v-if="!info" class="pad">
      <p class="dim">读取助手配置…</p>
    </div>

    <div v-else-if="info.auth_mode === 'missing'" class="pad">
      <StateBlock kind="empty" title="未接入数据源"
                  :detail="info.mode_reason"
                  hint='助手用真实数据回答；请先 pip install ".[data]" 或配置凭证后重启。' />
    </div>

    <div v-else-if="!ready" class="pad">
      <StateBlock kind="empty" title="AI 助手未配置模型"
                  hint="在 ~/.wmshare/credentials.env 或环境变量设置三个键：WMSHARE_LLM_API_KEY（必填）、WMSHARE_LLM_BASEURL（默认 DeepSeek）、WMSHARE_LLM_MODEL（默认 deepseek-chat），保存后刷新本页。" />
    </div>

    <div v-else class="layout">
      <aside class="side">
        <button class="wb-btn new" type="button" @click="freshChat">＋ 新会话</button>
        <button v-for="s in sessions" :key="s.id" class="sess"
                :class="{ active: s.id === activeId }" type="button"
                :title="titleOf(s)" @click="pick(s.id)">
          <span class="t">{{ titleOf(s) }}</span>
          <span class="del" title="删除会话"
                @click.stop="remove(s.id)">×</span>
        </button>
        <p v-if="!sessions.length" class="dim">还没有会话</p>
      </aside>

      <div class="main">
        <div ref="scroller" class="scroll">
          <template v-if="messages.length || live">
            <AssistantMessage v-for="(m, i) in messages" :key="i"
                              :message="m" />
            <AssistantMessage v-if="live" :live="live" />
          </template>
          <div v-else class="empty">
            <p>问点什么（数据优先，不做投资建议）：</p>
            <div class="prompts">
              <button v-for="p in PROMPTS" :key="p" class="wb-btn"
                      type="button" @click="send(p)">{{ p }}</button>
            </div>
          </div>
        </div>
        <AssistantComposer :running="running" :disabled="sending"
                           :turn-error="turnError"
                           @send="send" @stop="stop" @retry="freshChat" />
      </div>
    </div>
  </PanelShell>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  min-height: 480px;
}

.side {
  border-right: 1px solid var(--wb-border-dim);
  padding: var(--wb-sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-2);
}

.new {
  margin-bottom: var(--wb-sp-2);
}

.sess {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--wb-sp-2);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--wb-r-2);
  color: var(--wb-text-secondary);
  font-size: var(--wb-fs-2);
  padding: var(--wb-sp-1) var(--wb-sp-2);
  cursor: pointer;
}

.sess.active {
  border-color: var(--wb-border-med);
  background: var(--wb-bg-hover);
}

.sess .t {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sess .del {
  color: var(--wb-text-tertiary);
  padding: 0 var(--wb-sp-1);
}

.sess .del:hover {
  color: var(--wb-up);
}

.dim {
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--wb-sp-4) 0;
  min-height: 420px;
  max-height: 66vh;
}

.empty {
  padding: var(--wb-sp-8) var(--wb-sp-6);
  color: var(--wb-text-secondary);
}

.prompts {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--wb-sp-2);
  margin-top: var(--wb-sp-3);
}

.pad {
  padding: var(--wb-sp-6);
}

.dim {
  color: var(--wb-text-tertiary);
}
</style>
