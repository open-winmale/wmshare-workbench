<script setup lang="ts">
/**
 * 块级数据截止徽标：`截至 X`；date 为空渲染「截至未知」。
 *
 * **收敛规则**：块日期等于页顶「截至」时调用方不要渲染本组件——
 * 页级一个就够，逐块刷屏是噪音（页级 chip 在 `PanelShell`）。本组件
 * 只负责「一块数据自己的截止事实」：上游没给日期就如实说未知，
 * 不拿页级日期顶替、不编。复用全局 `wb-chip` 样式。
 */
withDefaults(defineProps<{
  /** 本块数据的截止日（YYYY-MM-DD）；空 = 上游未提供 */
  date?: string | null
  /** 文案前缀；历史期次类数据用不同措辞（如「报告期」） */
  label?: string
}>(), { date: '', label: '截至' })
</script>

<template>
  <span class="wb-chip" :title="date ? '' : '上游未提供该数据的截止日期'">
    {{ date ? `${label} ${date}` : `${label}未知` }}
  </span>
</template>
