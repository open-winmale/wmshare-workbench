<script setup lang="ts">
/**
 * 持仓档案：保存 / 载入。
 *
 * **为什么单独成组件**：保存与载入是「本地库读写」，与「估值计算」是两件
 * 不同的事。挤在 `PortfolioView` 里会越过单文件上限，也让人误以为保存会花钱。
 *
 * **载入只填回编辑器，不自动重算**：用户可能有未保存的修改，自动重算会让
 * 改动无声消失。填回去之后由他决定是否点「计算」。
 *
 * **列表用独立请求**，不复用 `useTool` 的 `load`：那个 `load` 会覆盖主页面的
 * 估值结果，档案列表刷新时表格会闪空。
 */
import { onMounted, ref } from 'vue'

import { run } from '../../api/client'

const props = defineProps<{
  /** 编辑器里的成交原文（保存时取其解析结果） */
  tradesText: string
}>()

const emit = defineEmits<{
  /** 载入成功：把成交数组交回父组件填进编辑器 */
  loaded: [trades: unknown[]]
}>()

const setName = ref('')
const sets = ref<string[]>([])
const note = ref('')
const busy = ref(false)

/** 拉档案名列表。失败不打扰用户——它不影响估值主流程。 */
function refresh(): Promise<void> {
  return run<{ sets?: string[] }>('portfolio', { action: 'list' })
    .then((env) => {
      sets.value = env.data?.sets ?? []
    })
    .catch(() => {
      // 档案列表读不到时保持上次的列表，不清空
    })
}

/** 保存当前成交为一套档案。**JSON 解析失败就地报**，不静默。 */
function save(): void {
  const name = setName.value.trim()
  let parsed: unknown
  try {
    parsed = JSON.parse(props.tradesText)
  } catch {
    note.value = '成交 JSON 解析失败，未保存'
    return
  }
  note.value = ''
  busy.value = true
  run<{ saved?: string }>('portfolio', { action: 'save', name, trades: parsed })
    .then((env) => {
      const saved = env.data?.saved
      note.value = saved
        ? `已保存「${String(saved)}」`
        : '保存未返回档案名'
      return refresh()
    })
    .catch((exc: unknown) => {
      note.value = exc instanceof Error ? exc.message : String(exc)
    })
    .finally(() => {
      busy.value = false
    })
}

/** 载入一套档案：只把内容交回父组件，**不自动重算**。 */
function loadSet(name: string): void {
  note.value = ''
  busy.value = true
  run<{ trades?: unknown[] }>('portfolio', { action: 'load', name })
    .then((env) => {
      const got = env.data?.trades
      if (!Array.isArray(got)) {
        note.value = `档案「${name}」内容为空`
        return
      }
      emit('loaded', got)
      note.value = `已载入「${name}」（${got.length} 笔），点「计算」重新估值`
    })
    .catch((exc: unknown) => {
      note.value = exc instanceof Error ? exc.message : String(exc)
    })
    .finally(() => {
      busy.value = false
    })
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div>
    <div class="wb-bar bar">
      <input v-model="setName" class="wb-input w160" type="text"
             placeholder="档案名，如 主仓" />
      <button class="wb-btn" type="button" :disabled="busy" @click="save">
        保存为档案
      </button>
      <span class="spacer" />
      <span v-if="!sets.length" class="wb-dim">暂无档案</span>
      <button v-for="s in sets" :key="s" class="wb-tab" type="button"
              :disabled="busy" @click="loadSet(s)">
        载入「{{ s }}」
      </button>
    </div>
    <p v-if="note" class="note">{{ note }}</p>
  </div>
</template>

<style scoped>
.bar {
  border-bottom: none;
  padding-top: 0;
}

.w160 {
  width: 160px;
}

.spacer {
  flex: 1;
}

.note {
  margin: 0;
  padding: 0 var(--wb-sp-6) var(--wb-sp-3);
  color: var(--wb-text-secondary);
  font-size: var(--wb-fs-2);
}
</style>
