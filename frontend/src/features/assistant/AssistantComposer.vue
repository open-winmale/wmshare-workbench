<script setup lang="ts">
/**
 * 助手输入条 + 运行中可停。错误以行内提示给处置按钮（信封 action 语义）。
 */
import { ref } from 'vue'

import { ACTION_LABEL } from '../../composables/useTool'

const props = defineProps<{
  running: boolean
  disabled: boolean
  turnError: { message: string; action: string } | null
}>()

const emit = defineEmits<{ send: [text: string]; stop: []; retry: [] }>()

const draft = ref('')

function submit(): void {
  const text = draft.value.trim()
  if (!text || props.disabled) return
  draft.value = ''
  emit('send', text)
}

function onKeydown(event: KeyboardEvent): void {
  // Enter 发送、Shift+Enter 换行（与平台助手的输入约定一致）
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="composer">
    <div v-if="turnError" class="err">
      <span class="msg">{{ turnError.message }}</span>
      <button class="wb-btn" type="button"
              @click="emit('retry')">
        {{ ACTION_LABEL[turnError.action as keyof typeof ACTION_LABEL] ?? '重试' }}
      </button>
    </div>
    <div class="bar">
      <textarea
        v-model="draft"
        class="wb-input grow"
        rows="2"
        placeholder="问数据问题，如：600519 现在多少钱 / 最近一年哪些行业涨得多（Enter 发送，Shift+Enter 换行）"
        :disabled="disabled"
        @keydown="onKeydown"
      />
      <button v-if="running" class="wb-btn" type="button" @click="emit('stop')">
        停止
      </button>
      <button v-else class="wb-btn" type="button" :disabled="disabled"
              @click="submit()">
        发送
      </button>
    </div>
  </div>
</template>

<style scoped>
.composer {
  padding: var(--wb-sp-3) var(--wb-sp-6);
  border-top: 1px solid var(--wb-border-dim);
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-2);
}

.err {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--wb-sp-3);
  border: 1px solid var(--wb-up);
  border-radius: var(--wb-r-2);
  padding: var(--wb-sp-2) var(--wb-sp-3);
  font-size: var(--wb-fs-2);
  color: var(--wb-up);
}

.bar {
  display: flex;
  align-items: flex-end;
  gap: var(--wb-sp-2);
}

.grow {
  flex: 1;
  resize: none;
  min-height: 56px;
}
</style>
