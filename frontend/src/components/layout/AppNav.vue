<script setup lang="ts">
/**
 * 侧栏导航（从 `App.vue` 拆出）。
 *
 * 拆出的理由不只是行数：导航的分组、选中态、移动端展开是**独立关注点**，
 * 和「应用装配 + 主题切换」混在一个文件里会让两者都难改。
 */
import { groupedTools, type ToolSlug } from '../../api/tools'

defineProps<{ current: ToolSlug; open: boolean }>()
const emit = defineEmits<{ navigate: [slug: ToolSlug] }>()
</script>

<template>
  <nav class="nav" :class="{ open }">
    <template v-for="g in groupedTools()" :key="g.group">
      <p class="group">{{ g.group }}</p>
      <button v-for="tool in g.tools" :key="tool.slug" class="item"
              :class="{ on: current === tool.slug }" type="button"
              :title="tool.hint" @click="emit('navigate', tool.slug)">
        {{ tool.title }}
      </button>
    </template>
  </nav>
</template>

<style scoped>
.nav {
  flex: 0 0 var(--wb-nav-w);
  border-right: 1px solid var(--wb-border-dim);
  background: var(--wb-bg-surface);
  padding: var(--wb-sp-5) var(--wb-sp-3);
  overflow-y: auto;
}

.group {
  margin: var(--wb-sp-5) var(--wb-sp-4) var(--wb-sp-2);
  font-size: var(--wb-fs-1);
  color: var(--wb-text-dim);
  letter-spacing: 0.06em;
}

.item {
  display: block;
  width: 100%;
  text-align: left;
  padding: var(--wb-sp-3) var(--wb-sp-4);
  background: transparent;
  border: none;
  border-radius: var(--wb-r-2);
  color: var(--wb-text-secondary);
  font-family: var(--wb-font-sans);
  font-size: var(--wb-fs-4);
  cursor: pointer;
}

.item:hover {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}

.item.on {
  color: var(--wb-accent);
  background: var(--wb-accent-bg);
  font-weight: 500;
}

@media (max-width: 820px) {
  .nav {
    display: none;
    position: absolute;
    top: var(--wb-topbar-h);
    left: 0;
    right: 0;
    z-index: var(--wb-z-dropdown);
    border-bottom: 1px solid var(--wb-border-med);
    max-height: 60vh;
  }

  .nav.open {
    display: block;
  }
}
</style>
