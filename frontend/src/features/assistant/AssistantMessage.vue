<script setup lang="ts">
/**
 * 一条聊天消息（落定态）或一轮直播态（阶段胶囊 + 步骤 + 来源账）。
 *
 * 借鉴平台助手的交互范式（不搬代码）：流式草稿、「来源 n」芯片、
 * 阶段胶囊；本地工具不需要的（多席位 rack / 计费面板 / 乐观去重）不做。
 */
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

import type { ChatMessage, StreamSnapshot } from './types'

const props = defineProps<{
  message?: ChatMessage
  live?: StreamSnapshot | null
}>()

// html:false —— 原始 HTML 一律转义，模型输出不经消毒直接渲染也安全
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const content = computed(() => props.live?.text ?? props.message?.content ?? '')
const html = computed(() => md.render(content.value || ''))

const isUser = computed(() => !props.live && props.message?.role === 'user')
const sources = computed(() =>
  props.live ? props.live.sources : props.message?.sources ?? [])
const steps = computed(() => props.live?.steps ?? [])
</script>

<template>
  <div class="row" :class="{ user: isUser }">
    <div class="bubble" :class="{ user: isUser }">
      <!-- 直播态：阶段胶囊 + 做了什么 -->
      <div v-if="live" class="caps">
        <span class="phase">{{ live.phase }}</span>
      </div>
      <div v-if="content" class="md" v-html="html" />
      <div v-else-if="live" class="thinking">…</div>
      <!-- 直播态的取数步骤（做了什么，逐条可读） -->
      <ul v-if="live && steps.length" class="steps">
        <li v-for="(s, i) in steps" :key="i">取数：{{ s.tool }} {{ s.brief }}</li>
      </ul>
      <!-- 来源账：宿主编号的证据，成稿 [n] 与这里一一对应 -->
      <div v-if="sources.length" class="src">
        <span class="label">来源</span>
        <span v-for="s in sources" :key="s.n" class="chip"
              :title="`${s.kind} · ${s.detail}${s.as_of ? ' · 截至 ' + s.as_of : ''}`">
          [{{ s.n }}] {{ s.title }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  padding: var(--wb-sp-2) var(--wb-sp-6);
}

.row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: min(760px, 92%);
  padding: var(--wb-sp-3) var(--wb-sp-4);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-3);
  background: var(--wb-bg-surface);
  min-width: 0;
}

.bubble.user {
  background: var(--wb-bg-inset, var(--wb-bg-surface));
  border-color: var(--wb-border-med);
  white-space: pre-wrap;
}

.caps {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-2);
  margin-bottom: var(--wb-sp-2);
}

.phase {
  font-size: var(--wb-fs-2);
  color: var(--wb-info);
  border: 1px solid var(--wb-info);
  border-radius: var(--wb-r-5);
  padding: 0 var(--wb-sp-2);
}

.thinking {
  color: var(--wb-text-tertiary);
}

.steps {
  margin: var(--wb-sp-2) 0 0;
  padding-left: var(--wb-sp-4);
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.src {
  display: flex;
  flex-wrap: wrap;
  gap: var(--wb-sp-1);
  margin-top: var(--wb-sp-3);
  align-items: center;
}

.src .label {
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.chip {
  font-size: var(--wb-fs-2);
  color: var(--wb-text-secondary);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-5);
  padding: 0 var(--wb-sp-2);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}

/* markdown 正文（表格/代码随设计令牌走，无裸色值） */
.md :deep(p) {
  margin: 0 0 var(--wb-sp-2);
}

.md :deep(p:last-child) {
  margin-bottom: 0;
}

.md :deep(table) {
  border-collapse: collapse;
  margin: var(--wb-sp-2) 0;
}

.md :deep(th),
.md :deep(td) {
  border: 1px solid var(--wb-border-dim);
  padding: var(--wb-sp-1) var(--wb-sp-2);
  font-size: var(--wb-fs-2);
}

.md :deep(code) {
  font-family: var(--wb-font-mono);
  background: var(--wb-bg-inset, transparent);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-1);
  padding: 0 var(--wb-sp-1);
}

.md :deep(ul),
.md :deep(ol) {
  margin: var(--wb-sp-2) 0;
  padding-left: var(--wb-sp-5);
}
</style>
