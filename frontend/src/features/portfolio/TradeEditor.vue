<script setup lang="ts">
/**
 * 成交编辑器（从 `PortfolioView` 拆出）。
 *
 * **JSON 解析错误必须就地显示**，不能悄悄回退到上一次结果——
 * 用户改了一笔数字却发现表没变，会以为计算是坏的。
 */
import { ref } from 'vue'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: [trades: unknown]
}>()

const parseError = ref('')

function update(event: Event): void {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}

function run(): void {
  parseError.value = ''
  let parsed: unknown
  try {
    parsed = JSON.parse(props.modelValue)
  } catch (exc) {
    parseError.value = `成交 JSON 非法：${exc instanceof Error ? exc.message : exc}`
    return
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    parseError.value = '成交必须是非空数组'
    return
  }
  emit('submit', parsed)
}
</script>

<template>
  <div class="editor">
    <label class="label">成交（JSON，按日期回放）</label>
    <textarea class="wb-textarea" :value="modelValue" spellcheck="false"
              @input="update" />
    <div class="actions">
      <button class="wb-btn" type="button" @click="run">计算</button>
      <span v-if="parseError" class="err">{{ parseError }}</span>
    </div>
  </div>
</template>

<style scoped>
.editor {
  padding: var(--wb-sp-4) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

.label {
  display: block;
  font-size: var(--wb-fs-1);
  color: var(--wb-text-tertiary);
  margin-bottom: var(--wb-sp-2);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-4);
  margin-top: var(--wb-sp-3);
}

.err {
  color: var(--wb-up);
  font-size: var(--wb-fs-2);
}
</style>
