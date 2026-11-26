<script setup lang="ts">
/**
 * 行情（`/api/markets/run`）：全市场宽度与涨跌榜。
 *
 * 与「自选」的分工：自选是「你关心的几只」，这一页是「整个市场的概览」。
 */
import { computed, onMounted } from 'vue'

import BarChart from '../../components/ui/BarChart.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { money, pct, trendClass } from '../../composables/format'

interface Breadth {
  up?: number
  down?: number
  flat?: number
  limit_up?: number
  limit_down?: number
  median_pct?: number
}

interface BinRow {
  bin: string
  count: number | null
}

interface MoverRow {
  symbol: string
  name: string
  percent: number | null
}

interface FlowRow {
  symbol: string
  name: string
  net_mf: number | null
  net_mv_ratio: number | null
  elg_net: number | null
  lg_net: number | null
}

interface MarketsData {
  kpi: Breadth
  breadth: Record<string, unknown>
  bins: BinRow[]
  movers: MoverRow[]
  moneyflow: FlowRow[]
  /** 最新交易日（推断口径：沪深300最新K线日；上游宽度/资金流不标注日期） */
  trading_day?: string
  sources: string[]
}

const { data, loading, error, asOf, warnings, load } =
  useTool<MarketsData>('markets')

const kpis = computed<Kpi[]>(() => {
  const b = data.value?.kpi ?? {}
  return [
    { key: 'up', label: '上涨', value: b.up ?? '—', tone: 'bad' },
    { key: 'down', label: '下跌', value: b.down ?? '—', tone: 'ok' },
    { key: 'flat', label: '平盘', value: b.flat ?? '—', tone: 'muted' },
    { key: 'lu', label: '涨停', value: b.limit_up ?? '—', tone: 'bad' },
    { key: 'ld', label: '跌停', value: b.limit_down ?? '—', tone: 'ok' },
    {
      key: 'med',
      label: '涨跌中位',
      value: b.median_pct === undefined ? '—' : pct(b.median_pct),
      tone: 'muted',
    },
  ]
})

const bins = computed(() =>
  (data.value?.bins ?? []).map((b) => ({ label: b.bin, value: b.count })),
)

const moverColumns: Column[] = [
  { key: 'symbol', label: '代码', mono: true, dim: true },
  { key: 'name', label: '名称' },
  { key: 'percent', label: '涨跌幅', numeric: true },
]

const flowColumns: Column[] = [
  { key: 'symbol', label: '代码', mono: true, dim: true },
  { key: 'name', label: '名称' },
  { key: 'net_mf', label: '主力净流入', numeric: true },
  { key: 'net_mv_ratio', label: '占市值', numeric: true, dim: true },
]

function asMover(item: Record<string, unknown>): MoverRow {
  return item as unknown as MoverRow
}

function asFlow(item: Record<string, unknown>): FlowRow {
  return item as unknown as FlowRow
}

onMounted(() => load({}))
</script>

<template>
  <PanelShell title="行情" subtitle="全市场宽度由服务端索引聚合直出，未在客户端重算"
              :as-of="asOf" :loading="loading" @refresh="load({})">
    <template #actions>
      <!-- 宽度/资金流上游不标注数据日期；「最新交易日」是推断口径
           （沪深300最新K线日），不是数据截止——所以不写成「截至」 -->
      <span v-if="data?.trading_day" class="wb-chip"
            title="推断口径：上游宽度/资金流接口未标注数据日期，以沪深300最新K线交易日为准">
        最新交易日 {{ data.trading_day }}
      </span>
      <span v-else-if="!asOf" class="wb-chip"
            title="上游接口未提供本页数据的截止日期">截至未知</span>
    </template>
    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock v-else-if="error" kind="error" title="读取失败" :detail="error.message"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="load({})" />

    <template v-else>
      <KpiStrip :items="kpis" />

      <p v-for="w in warnings" :key="w" class="wb-warn">{{ w }}</p>

      <div class="grid">
        <div class="wb-card">
          <h2>涨跌幅分布</h2>
          <BarChart :bars="bins" tone="updown" :height="240" />
        </div>
        <div class="wb-card">
          <h2>涨跌榜（按振幅）</h2>
          <DataTable :columns="moverColumns"
                     :rows="(data?.movers ?? []) as unknown as Record<string, unknown>[]"
                     empty-text="无涨跌榜数据">
            <template #percent="{ row }">
              <span :class="trendClass(asMover(row).percent)">
                {{ pct(asMover(row).percent) }}
              </span>
            </template>
          </DataTable>
        </div>
      </div>

      <div class="wb-card wide">
        <h2>主力净流入前列</h2>
        <DataTable :columns="flowColumns"
                   :rows="(data?.moneyflow ?? []) as unknown as Record<string, unknown>[]"
                   empty-text="无资金流数据">
          <template #net_mf="{ row }">
            <span :class="trendClass(asFlow(row).net_mf)">
              {{ money(asFlow(row).net_mf) }}
            </span>
          </template>
          <template #net_mv_ratio="{ row }">
            {{ pct(asFlow(row).net_mv_ratio) }}
          </template>
        </DataTable>
      </div>
    </template>
  </PanelShell>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(300px, 1fr);
  gap: var(--wb-sp-6);
  padding: var(--wb-sp-6);
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.wide {
  padding: 0 var(--wb-sp-6) var(--wb-sp-6);
}

h2 {
  margin: 0 0 var(--wb-sp-4);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}
</style>
