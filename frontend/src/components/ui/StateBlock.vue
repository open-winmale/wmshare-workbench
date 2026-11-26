<script setup lang="ts">
/** 五态里的三态（loading / empty / error）统一外观，避免每页重写。 */
defineProps<{
  kind: 'empty' | 'error'
  title: string
  detail?: string
  hint?: string
  actionLabel?: string
}>()

const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <div class="state" :class="kind">
    <div class="title">{{ title }}</div>
    <p v-if="detail">{{ detail }}</p>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <button v-if="actionLabel" class="btn" type="button" @click="emit('action')">
      {{ actionLabel }}
    </button>
  </div>
</template>

<style scoped>
.state {
  padding: var(--wb-sp-9);
  text-align: center;
}

.title {
  font-size: var(--wb-fs-5);
  margin-bottom: var(--wb-sp-4);
}

.state.error .title {
  color: var(--wb-up);
}

.state.empty .title {
  color: var(--wb-warning);
}

.hint {
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
  max-width: 42em;
  margin: var(--wb-sp-4) auto;
}

.btn {
  font-family: var(--wb-font-mono);
  font-size: var(--wb-fs-2);
  padding: var(--wb-sp-2) var(--wb-sp-5);
  background: var(--wb-bg-raised);
  color: var(--wb-text-secondary);
  border: 1px solid var(--wb-border-med);
  border-radius: var(--wb-r-2);
  cursor: pointer;
  margin-top: var(--wb-sp-4);
}

.btn:hover {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}
</style>
