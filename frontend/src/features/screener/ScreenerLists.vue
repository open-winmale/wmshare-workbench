<script setup lang="ts">
/**
 * 选股侧栏：示例表达式 + 已保存策略（从 View 拆出，保住 250 行上限）。
 *
 * 回填动作相同：回填表达式**原文**后立即重跑——保存的策略不固化
 * 非负守卫（守卫是执行口径，按当次开关重新追加）。
 */
export interface Preset {
  name: string
  where: string
}

export interface SavedScreen {
  name: string
  where: string
  order?: string
  created_at?: string
}

defineProps<{ presets: Preset[]; saved: SavedScreen[] }>()
const emit = defineEmits<{ use: [expr: string] }>()
</script>

<template>
  <div class="sides">
    <div class="side">
      <h2>示例表达式</h2>
      <button v-for="p in presets" :key="p.name" class="link"
              type="button" @click="emit('use', p.where)">
        {{ p.name }}
      </button>
    </div>
    <div class="side">
      <h2>已保存策略</h2>
      <p v-if="!saved.length" class="dim">还没有保存的策略</p>
      <button v-for="s in saved" :key="s.name" class="link"
              type="button" :title="s.where" @click="emit('use', s.where)">
        {{ s.name }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.sides {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--wb-sp-6);
  padding: var(--wb-sp-5) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

.side {
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-2);
  min-width: 0;
}

h2 {
  margin: 0 0 var(--wb-sp-2);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.link {
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--wb-r-2);
  color: var(--wb-info);
  font-family: var(--wb-font-mono);
  font-size: var(--wb-fs-2);
  padding: var(--wb-sp-1) var(--wb-sp-2);
  cursor: pointer;
}

.link:hover {
  border-color: var(--wb-border-med);
  background: var(--wb-bg-hover);
}
</style>
