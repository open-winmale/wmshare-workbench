<script setup lang="ts">
/**
 * 页面骨架：标题 + 副标题 + 右侧操作区 + 内容。
 *
 * **为什么要这个组件**：九个工具页的头部结构完全一样。不抽出来的话，
 * 每个页面各写一遍「h1 + 说明 + 刷新按钮」，几轮之后标题字号、间距、
 * 按钮位置就会各不相同——这是最早出现、最难察觉的 UI 腐化形态。
 */
defineProps<{
  title: string
  subtitle?: string
  /** 数据截至日（空字符串则不显示） */
  asOf?: string
  loading?: boolean
}>()

const emit = defineEmits<{ refresh: [] }>()
</script>

<template>
  <section class="panel">
    <header class="head">
      <div class="titles">
        <h1>{{ title }}</h1>
        <p v-if="subtitle" class="sub">{{ subtitle }}</p>
      </div>
      <span v-if="asOf" class="asof">截至 {{ asOf }}</span>
      <slot name="actions" />
      <button class="wb-btn btn" type="button" :disabled="loading"
              @click="emit('refresh')">
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.panel {
  background: var(--wb-bg-surface);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-3);
  box-shadow: var(--wb-shadow-1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.head {
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-5);
  padding: var(--wb-sp-6) var(--wb-sp-8);
  border-bottom: 1px solid var(--wb-border-dim);
  flex-wrap: wrap;
}

.titles {
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-5);
  flex-wrap: wrap;
  min-width: 0;
}

h1 {
  margin: 0;
  font-size: var(--wb-fs-6);
  font-weight: 600;
}

.sub {
  margin: 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.asof {
  font-size: var(--wb-fs-1);
  color: var(--wb-text-dim);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-5);
  padding: 0 var(--wb-sp-3);
}

.btn {
  margin-left: auto;
}
</style>
