<script setup lang="ts">
/**
 * 通用表格：斑马纹、吸顶表头、数值列右对齐。
 *
 * **数值列排序键必须独立于显示文本**（`DESIGN_SYSTEM` §4 铁律 1）：
 * `1.2万` 要按 12000 排，不能按字符串排。故 `column.numeric` 的单元格
 * 要求调用方同时给出 `sort` 值；本组件只负责渲染与对齐。
 */
export interface Column {
  key: string
  label: string
  numeric?: boolean
  mono?: boolean
  dim?: boolean
}

withDefaults(
  defineProps<{ columns: Column[]; rows: Record<string, unknown>[]; emptyText?: string }>(),
  { emptyText: '无数据' },
)
</script>

<template>
  <table class="wb-table">
    <thead>
      <tr>
        <th
          v-for="c in columns"
          :key="c.key"
          :class="{ num: c.numeric }"
        >{{ c.label }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(r, i) in rows" :key="i">
        <td
          v-for="c in columns"
          :key="c.key"
          :class="{ num: c.numeric, mono: c.mono, dim: c.dim }"
        >
          <slot :name="c.key" :row="r" :value="r[c.key]">{{ r[c.key] }}</slot>
        </td>
      </tr>
      <tr v-if="rows.length === 0">
        <td :colspan="columns.length" class="empty">{{ emptyText }}</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.wb-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wb-fs-3);
}

th {
  text-align: left;
  font-weight: 500;
  color: var(--wb-text-tertiary);
  padding: var(--wb-sp-3) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-med);
  background: var(--wb-bg-raised);
  white-space: nowrap;
}

td {
  padding: var(--wb-sp-3) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

tbody tr:nth-child(even) {
  background: var(--wb-row-alt);
}

tbody tr:hover {
  background: var(--wb-bg-hover);
}

.num {
  text-align: right;
  font-family: var(--wb-font-mono);
  font-variant-numeric: tabular-nums;
}

.mono {
  font-family: var(--wb-font-mono);
}

.dim {
  color: var(--wb-text-dim);
}

.empty {
  text-align: center;
  color: var(--wb-text-tertiary);
  padding: var(--wb-sp-9);
}
</style>
