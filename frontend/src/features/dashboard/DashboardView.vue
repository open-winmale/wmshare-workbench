<script setup lang="ts">
/**
 * 驾驶舱（`/api/dashboard/run`）。
 *
 * 这是打开工作台就看的第一页，所以它只用 AUTO 级数据源（指数聚合），
 * 不含任何付费重请求——后端有断言保证。
 */
import { computed, onMounted } from 'vue'

import AsOfChip from '../../components/ui/AsOfChip.vue'
import BarChart from '../../components/ui/BarChart.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { money, num, pct, trendClass } from '../../composables/format'
import DashboardIndices, { type IndexCard } from './DashboardIndices.vue'
import DashboardPulse, { type PulseData } from './DashboardPulse.vue'

interface IndexRow {
  key: string
  label: string
  pe: number | null
  pb: number | null
  dv: number | null
  /** PE/PB 的数据日（index.trend 末点=最新交易日）；回退季度口径时为空 */
  pe_date?: string
  /** true = PE/PB 来自季度末回退（该指数无最新交易日估值） */
  quarterly?: boolean
}

interface Breadth {
  up?: number
  down?: number
  flat?: number
  limit_up?: number
  limit_down?: number
  median_pct?: number
}

interface FlowRow {
  symbol: string
  name: string
  net_mf: number | null
}

interface DashData {
  /** 今日盘面三卡（date 守卫后；上游兜底假行不会出现） */
  index_cards?: IndexCard[]
  /** 涨跌分布直方图 + 涨跌幅双榜 */
  distribution?: PulseData
  indices: IndexRow[]
  index_note: string
  /** PE/PB 的数据日（最新交易日）；股息率与回退口径另见 dv_as_of */
  indices_as_of?: string
  /** 股息率的季度末口径日期（上游 indices.valuation 为季频采样） */
  dv_as_of?: string
  /** 最新交易日（推断口径：沪深300最新K线日；宽度/资金流上游不标注日期） */
  trading_day?: string
  breadth: Breadth
  breadth_note: string
  moneyflow: FlowRow[]
  moneyflow_note: string
  manual_calls: number
}

const { data, loading, error, asOf, load } = useTool<DashData>('dashboard')

const kpis = computed<Kpi[]>(() => {
  const b = data.value?.breadth ?? {}
  // **字段缺失就不占位置**：真实 ``screener.index_breadth_summary`` 只给
  // up/down/flat/total/各 pct/median_pct，**没有** limit_up/limit_down。
  // 固定给它俩一个格子会渲染成「涨停 —」，像数据坏了；而它根本没这个字段。
  // 指数不再进 KpiStrip——盘面三卡（DashboardIndices）取而代之。
  const items: Kpi[] = [
    { key: 'up', label: '上涨', value: b.up ?? '—', tone: 'bad' },
    { key: 'down', label: '下跌', value: b.down ?? '—', tone: 'ok' },
    { key: 'flat', label: '平盘', value: b.flat ?? '—', tone: 'muted' },
  ]
  if (b.limit_up !== undefined && b.limit_up !== null) {
    items.push({ key: 'lu', label: '涨停', value: b.limit_up, tone: 'bad' })
  }
  if (b.limit_down !== undefined && b.limit_down !== null) {
    items.push({ key: 'ld', label: '跌停', value: b.limit_down, tone: 'ok' })
  }
  if (b.median_pct !== undefined && b.median_pct !== null) {
    items.push({
      key: 'med', label: '涨跌中位', value: pct(b.median_pct), tone: 'muted',
    })
  }
  return items
})

const indexColumns: Column[] = [
  { key: 'label', label: '指数' },
  { key: 'pe', label: 'PE', numeric: true },
  { key: 'pb', label: 'PB', numeric: true },
  { key: 'dv', label: '股息率', numeric: true },
]

const flowColumns: Column[] = [
  { key: 'symbol', label: '代码', mono: true, dim: true },
  { key: 'name', label: '名称' },
  { key: 'net_mf', label: '主力净流入', numeric: true },
]

const flowBars = computed(() =>
  (data.value?.moneyflow ?? []).map((r) => ({
    label: r.name || r.symbol,
    value: r.net_mf,
  })),
)

function asRecord(row: Record<string, unknown>): IndexRow & FlowRow {
  return row as unknown as IndexRow & FlowRow
}

onMounted(() => load({}))
</script>

<template>
  <PanelShell title="驾驶舱" :subtitle="data?.index_note ?? '指数估值 · 涨跌宽度 · 资金流'"
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
                hint="驾驶舱只用免费级数据源；失败通常是后端未启动或凭证失效。"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="load({})" />

    <template v-else>
      <KpiStrip :items="kpis" />

      <!-- 今日盘面：三大指数卡（现价/涨跌/分时 mini/高低）+ 分布与双榜 -->
      <DashboardIndices :cards="data?.index_cards ?? []" />
      <DashboardPulse :dist="data?.distribution ?? {}" />

      <div class="grid">
        <div class="wb-card">
          <h2 class="card-head">
            主要指数估值
            <AsOfChip :date="data?.indices_as_of" />
          </h2>
          <DataTable :columns="indexColumns"
                     :rows="(data?.indices ?? []) as unknown as Record<string, unknown>[]"
                     empty-text="无可用指数估值">
            <template #label="{ row }">
              {{ asRecord(row).label }}
              <!-- 回退口径必须可见：季末数据不能看起来像今日值 -->
              <span v-if="asRecord(row).quarterly" class="wb-chip"
                    title="该指数无最新交易日估值，PE/PB 为季度末口径">季度</span>
            </template>
            <template #pe="{ value }">{{ num(value as number) }}</template>
            <template #pb="{ value }">{{ num(value as number) }}</template>
            <template #dv="{ value }">{{ pct(value as number) }}</template>
          </DataTable>
          <p class="wb-hint">
            PE/PB 为最新交易日估值；股息率为季度末口径<template
              v-if="data?.dv_as_of">（截至 {{ data.dv_as_of }}）</template>。
          </p>
        </div>

        <div class="wb-card">
          <h2 class="card-head">
            主力净流入前列
            <!-- 上游资金流无日期字段：按页级推断口径归置（label 说明
                 这是推断，不是上游标注） -->
            <AsOfChip :date="data?.trading_day" label="属" />
          </h2>
          <BarChart :bars="flowBars" tone="updown" format="money" horizontal
                    :height="190" />
          <DataTable :columns="flowColumns"
                     :rows="(data?.moneyflow ?? []) as unknown as Record<string, unknown>[]"
                     empty-text="无资金流数据">
            <template #net_mf="{ row }">
              <span :class="trendClass(asRecord(row).net_mf)">
                {{ money(asRecord(row).net_mf) }}
              </span>
            </template>
          </DataTable>
        </div>
      </div>

      <p v-if="data?.breadth_note || data?.moneyflow_note" class="note">
        <template v-if="data?.breadth_note">{{ data.breadth_note }}　</template>
        <template v-if="data?.moneyflow_note">{{ data.moneyflow_note }}</template>
      </p>
      <!-- 日期统一由页头「最新交易日」chip 收敛：宽度/资金流与 PE/PB 同属
           最新交易日，股息率的季度口径已在卡内标注，块级不再重复 -->
    </template>
  </PanelShell>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.4fr);
  gap: var(--wb-sp-6);
  padding: var(--wb-sp-6);
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

h2 {
  margin: 0 0 var(--wb-sp-4);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.card-head {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-3);
}

.note {
  margin: 0;
  padding: 0 var(--wb-sp-6) var(--wb-sp-5);
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}
</style>
