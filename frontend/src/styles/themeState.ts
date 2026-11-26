import { ref } from 'vue'

/**
 * 主题的**响应式镜像**（`App.vue` 写入，图表组件读取）。
 *
 * 为什么要这一份：图表色值在渲染时用 `getComputedStyle` 读 CSS 令牌，
 * 而 ECharts 的 option 是普通 computed——不依赖任何响应式状态，切主题后
 * 不会自动重画，亮色页面里会残留一套暗色图表（这个 bug 只在切主题时
 * 暴露，和「演示态全绿、真实态才崩」是同一类错）。把主题做成 ref，
 * 图表 `watch` 它触发重渲染。
 */
export const themeName = ref<'obsidian' | 'daylight'>('daylight')
export const cvdOn = ref(false)
