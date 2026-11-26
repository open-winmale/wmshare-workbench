<script setup lang="ts">
/**
 * 持仓账本（`/api/portfolio/run`）。
 *
 * 页面把三件账本事实显式展示出来（它们都是「显示错了也看着正常」的地方）：
 *
 * 1. **有价 / 总数**：合计只覆盖有价标的，缺价的必须标出来。
 * 2. **五法对比**：同一份成交换批次法的结果差异，直接并排显示。
 * 3. **价格与汇率拆分**：两个分量之和等于总盈亏（可对账）。
 */
import { computed, onMounted, ref } from 'vue'

import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import PortfolioArchive from './PortfolioArchive.vue'
import PortfolioMethods from './PortfolioMethods.vue'
import TradeEditor from './TradeEditor.vue'
import { DEFAULT_TRADES } from './sample'
import { money, price, qty } from '../../composables/format'
import { loadPref, savePref } from '../../composables/prefs'

interface Row {
  code: string
  /** 名称来自定价批量快照（23 字段），定价失败时为「—」 */
  name?: string
  shares: number
  avg_price: number | null
  price: number | null
  fx: number | null
  cost: number | null
  value: number | null
  unrealized: number | null
  realized: number | null
}

interface Totals {
  value: number | null
  cost: number | null
  realized: number | null
  unrealized: number | null
  valued: number
  total: number
  complete: boolean
}

interface MethodRow {
  method: string
  realized?: number | null
  unrealized?: number | null
  value?: number | null
  valued?: number
  total?: number
  error?: string
}

interface PortfolioData {
  method: string
  methods: string[]
  rows: Row[]
  totals: Totals
  by_method: MethodRow[]
  /** 有价标的的定价日（来自快照 kline_date）；整批同日则 min == max */
  priced_as_of?: string
  price_date_min?: string
  price_date_max?: string
  /** save/list/load 的返回块 */
  saved?: string
  n_trades?: number
  sets?: string[]
  name?: string
  trades?: unknown[]
}

const { data, loading, error, asOf, warnings, load } =
  useTool<PortfolioData>('portfolio')
// 上次的成交明细与批次法（P5-01 轻量持久化：只恢复输入，不自动计算）
const trades = ref(loadPref('pf.trades', DEFAULT_TRADES))
const method = ref(loadPref('pf.method', 'FIFO'))

const kpis = computed<Kpi[]>(() => {
  const t = data.value?.totals
  if (!t) return []
  return [
    { key: 'value', label: '市值', value: money(t.value), tone: 'muted',
      hint: `有价 ${t.valued}/${t.total}` },
    { key: 'cost', label: '成本', value: money(t.cost), tone: 'muted' },
    { key: 'unreal', label: '未实现', value: money(t.unrealized),
      tone: (t.unrealized ?? 0) >= 0 ? 'bad' : 'ok' },
    { key: 'real', label: '已实现', value: money(t.realized),
      tone: (t.realized ?? 0) >= 0 ? 'bad' : 'ok' },
    { key: 'cover', label: '有价', value: `${t.valued}/${t.total}`,
      tone: t.complete ? 'muted' : 'warn' },
  ]
})

const rowColumns: Column[] = [
  { key: 'code', label: '代码', mono: true, dim: true },
  { key: 'name', label: '名称' },
  { key: 'shares', label: '股数', numeric: true },
  { key: 'avg_price', label: '均价', numeric: true },
  { key: 'price', label: '现价', numeric: true },
  { key: 'cost', label: '成本', numeric: true },
  { key: 'value', label: '市值', numeric: true },
  { key: 'unrealized', label: '未实现', numeric: true },
  { key: 'realized', label: '已实现', numeric: true },
]

function asRow(item: Record<string, unknown>): Row {
  return item as unknown as Row
}

function onTrades(parsed: unknown): void {
  savePref('pf.trades', trades.value)
  savePref('pf.method', method.value)
  load({ action: 'valuate', trades: parsed, method: method.value })
}

function refresh(): void {
  run()
}

function run(): void {
  try {
    onTrades(JSON.parse(trades.value))
  } catch {
    // 解析错误由 TradeEditor 就地显示；这里保持上次结果不动
  }
}

onMounted(run)

/** 档案载入 → 填回编辑器（由用户决定是否重算）。 */
function onArchiveLoaded(got: unknown[]): void {
  trades.value = JSON.stringify(got, null, 2)
}
</script>

<template>
  <PanelShell title="持仓账本" subtitle="五法批次 · 价格/汇率拆分 · 合计只覆盖有价标的"
              :as-of="asOf" :loading="loading" @refresh="refresh()">
    <template #actions>
      <select v-model="method" class="wb-input" @change="run()">
        <option v-for="m in data?.methods ?? ['FIFO']" :key="m" :value="m">{{ m }}</option>
      </select>
    </template>

    <TradeEditor v-model="trades" @submit="onTrades" />

    <PortfolioArchive :trades-text="trades" @loaded="onArchiveLoaded" />

    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock v-else-if="error" kind="error" title="计算失败"
                :detail="error.message"
                hint="卖出超过持仓、批次法不匹配、日期乱序都会在这里报出来。"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="run()" />

    <template v-else>
      <KpiStrip :items="kpis" />

      <p v-for="w in warnings" :key="w" class="wb-warn">{{ w }}</p>

      <div class="wb-card">
        <h2 class="card-head">
          持仓（{{ data?.method }}）
          <span v-if="data?.priced_as_of" class="wb-chip"
                title="有价标的定价快照的日期（最大值）">
            定价 {{ data.priced_as_of }}
          </span>
        </h2>
        <p v-if="data?.price_date_min && data.price_date_min !== data.price_date_max"
           class="wb-hint">
          各标的定价日不一致：早至 {{ data.price_date_min }}，晚至
          {{ data.price_date_max }}（停牌票停在停牌前，页顶「截至」取最大值）。
        </p>
        <DataTable :columns="rowColumns"
                   :rows="(data?.rows ?? []) as unknown as Record<string, unknown>[]"
                   empty-text="没有持仓（可能已全部卖出）">
          <template #code="{ row }">
            <a class="rowlink" :href="`#/equity?sym=${asRow(row).code}`"
               :title="`查看 ${asRow(row).name || asRow(row).code} 的基本面`">
              {{ asRow(row).code }}
            </a>
          </template>
          <template #shares="{ row }">{{ qty(asRow(row).shares) }}</template>
          <template #avg_price="{ row }">{{ price(asRow(row).avg_price) }}</template>
          <template #price="{ row }">{{ price(asRow(row).price) }}</template>
          <template #cost="{ row }">{{ money(asRow(row).cost) }}</template>
          <template #value="{ row }">{{ money(asRow(row).value) }}</template>
          <template #unrealized="{ row }">{{ money(asRow(row).unrealized) }}</template>
          <template #realized="{ row }">{{ money(asRow(row).realized) }}</template>
        </DataTable>
      </div>

      <PortfolioMethods :methods="data?.by_method ?? []" />
    </template>
  </PanelShell>
</template>

<style scoped>
h2 {
  margin: var(--wb-sp-5) 0 var(--wb-sp-3);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.card-head {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-3);
}

.hint code {
  background: var(--wb-bg-raised);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-1);
  padding: 0 var(--wb-sp-1);
}

/* 行内代码 → 个股研究的跳转链接（与自选页同款：等宽 + hover 提亮） */
.rowlink {
  color: var(--wb-accent);
  text-decoration: none;
  font-family: var(--wb-font-mono);
}

.rowlink:hover {
  text-decoration: underline;
}
</style>
