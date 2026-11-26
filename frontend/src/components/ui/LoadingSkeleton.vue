<script setup lang="ts">
/** 骨架屏：保持布局不跳动（不用 spinner）。 */
withDefaults(defineProps<{ rows?: number }>(), { rows: 4 })
</script>

<template>
  <div class="skeleton">
    <div v-for="i in rows" :key="i" class="row" />
  </div>
</template>

<style scoped>
.skeleton {
  padding: var(--wb-sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--wb-sp-4);
}

.row {
  height: 32px;
  border-radius: var(--wb-r-2);
  background: linear-gradient(
    90deg,
    var(--wb-bg-raised) 0%,
    var(--wb-bg-hover) 50%,
    var(--wb-bg-raised) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s var(--wb-ease) infinite;
}

@keyframes shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}
</style>
