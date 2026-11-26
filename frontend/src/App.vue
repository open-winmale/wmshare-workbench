<script setup lang="ts">
/**
 * 应用外壳 = 状态条 + 侧栏 + 内容区。
 *
 * **路由用 hash 模式**（`#/dashboard`）：后端不需要 SPA fallback，
 * 刷新任意页面都直接命中 `index.html`（`docs/DEBT.md` D-11）。
 *
 * 本文件只做装配与主题切换；状态条与侧栏分别在
 * `components/layout/AppTopbar.vue` / `AppNav.vue`。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { get } from './api/client'
import { DEFAULT_SLUG, readHash, type ToolSlug } from './api/tools'
import { loadPref, savePref } from './composables/prefs'
import { cvdOn, themeName } from './styles/themeState'
import AppNav from './components/layout/AppNav.vue'
import AppTopbar, { type AppInfo } from './components/layout/AppTopbar.vue'
import AssistantView from './features/assistant/AssistantView.vue'
import BacktestView from './features/backtest/BacktestView.vue'
import DashboardView from './features/dashboard/DashboardView.vue'
import EstimateView from './features/ec/EstimateView.vue'
import EconomicsView from './features/economics/EconomicsView.vue'
import EquityView from './features/equity/EquityView.vue'
import MarketsView from './features/markets/MarketsView.vue'
import PortfolioView from './features/portfolio/PortfolioView.vue'
import ScreenerView from './features/screener/ScreenerView.vue'
import SourcesView from './features/sources/SourcesView.vue'
import WatchlistView from './features/watchlist/WatchlistView.vue'

const VIEWS = {
  dashboard: DashboardView,
  assistant: AssistantView,
  watchlist: WatchlistView,
  markets: MarketsView,
  equity: EquityView,
  screener: ScreenerView,
  economics: EconomicsView,
  backtest: BacktestView,
  portfolio: PortfolioView,
  sources: SourcesView,
  ec_estimate: EstimateView,
} as const

const info = ref<AppInfo | null>(null)
const infoError = ref('')
const current = ref<ToolSlug>(DEFAULT_SLUG)
const navOpen = ref(false)
const savedTheme = loadPref<string>('theme', 'daylight')
const theme = ref<'obsidian' | 'daylight'>(
  savedTheme === 'obsidian' ? 'obsidian' : 'daylight',
)
const cvd = ref(loadPref<boolean>('cvd', false))

const view = computed(() => VIEWS[current.value] ?? DashboardView)

function applyTheme(): void {
  // 同步给响应式镜像：图表组件 watch 它重渲染（getComputedStyle 的值
  // 变了但 computed option 不知道，不通知就会残留旧主题色）
  themeName.value = theme.value
  cvdOn.value = cvd.value
  document.documentElement.dataset.theme = theme.value
  if (cvd.value) document.documentElement.dataset.cvd = '1'
  else delete document.documentElement.dataset.cvd
}

function toggleTheme(): void {
  theme.value = theme.value === 'obsidian' ? 'daylight' : 'obsidian'
  savePref('theme', theme.value)
  applyTheme()
}

function toggleCvd(): void {
  cvd.value = !cvd.value
  savePref('cvd', cvd.value)
  applyTheme()
}

function syncHash(): void {
  current.value = readHash()
  navOpen.value = false
}

function navigate(slug: ToolSlug): void {
  if (window.location.hash === `#/${slug}`) current.value = slug
  else window.location.hash = `#/${slug}`
}

onMounted(async () => {
  applyTheme()
  syncHash()
  window.addEventListener('hashchange', syncHash)
  try {
    const env = await get<AppInfo>('appinfo')
    info.value = env.data
  } catch (exc) {
    infoError.value = exc instanceof Error ? exc.message : String(exc)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncHash)
})
</script>

<template>
  <div class="shell">
    <AppTopbar :info="info" :info-error="infoError" :theme="theme" :cvd="cvd"
               @toggle-theme="toggleTheme" @toggle-cvd="toggleCvd"
               @toggle-nav="navOpen = !navOpen" />

    <div class="body">
      <AppNav :current="current" :open="navOpen" @navigate="navigate" />
      <main class="content">
        <component :is="view" />
      </main>
    </div>

    <footer class="foot">
      数据来自 wmshare，最终以上市公司公告为准；本工具不构成投资建议。
    </footer>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--wb-bg-base);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.content {
  flex: 1;
  min-width: 0;
  padding: var(--wb-content-pad);
  overflow-y: auto;
}

.foot {
  flex: 0 0 auto;
  padding: var(--wb-sp-3) var(--wb-sp-6);
  border-top: 1px solid var(--wb-border-dim);
  color: var(--wb-text-dim);
  font-size: var(--wb-fs-1);
  background: var(--wb-bg-surface);
}
</style>
