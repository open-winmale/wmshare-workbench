<script setup lang="ts">
/**
 * 分段选择行（``wb-tab`` 按钮行的组件化收口，D-17 首次偿还）。
 *
 * 语义是「**单选**：一组互斥选项，高亮当前选中」——年限档位、报表期档、
 * 指数切换这类。排序开关/动作按钮不是单选（各只有 1 处，未到 D-17
 * 的触发线），不收敛进来。
 *
 * **多根模板**：只输出按钮本身；外层布局（flex 间距、行首说明、推开
 * 的 gap）由调用方持有——各页 subbar 形态略有差异，把布局抢进来反而
 * 限制表达。
 */
interface SegOption {
  value: string | number
  label: string
  title?: string
}

defineProps<{
  options: readonly SegOption[]
  selected?: string | number
}>()

const emit = defineEmits<{ pick: [value: string | number] }>()
</script>

<template>
  <button v-for="o in options" :key="o.value" class="wb-tab"
          :class="{ on: selected === o.value }" type="button"
          :title="o.title ?? o.label" @click="emit('pick', o.value)">
    {{ o.label }}
  </button>
</template>
