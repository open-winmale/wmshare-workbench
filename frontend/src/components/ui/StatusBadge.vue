<script setup lang="ts">
/** 状态角标：颜色不是唯一载体——必须同时有文字。 */
defineProps<{ tone: 'fresh' | 'stale' | 'expired' | 'unknown'; text: string }>()
</script>

<template>
  <span class="badge" :class="tone">{{ text }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  font-size: var(--wb-fs-1);
  padding: 0 var(--wb-sp-3);
  border-radius: var(--wb-r-5);
  border: 1px solid currentColor;
}

.badge.fresh {
  color: var(--wb-down);
}

.badge.stale {
  color: var(--wb-warning);
}

.badge.expired {
  color: var(--wb-up);
}

.badge.unknown {
  color: var(--wb-text-tertiary);
}
</style>
