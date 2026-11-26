<script setup lang="ts">
/**
 * 回测（`/api/backtest/run`）。
 *
 * **必须显式传区间**：不给区间会取全历史（数十万 EC 量级），后端会拒绝。
 * 页面默认填「近两年」，让用户不必先撞一次墙。
 *
 * 买卖点标在价格 K 线上（不是净值上）；价格 K 线是后端另取的一次
 * `kline.bars`（信封 meta 披露），取不到时降级为仅净值曲线。
 */
import { computed, onMounted, ref } from 'vue'

import type { Bar, Mark } from '../../components/ui/KLineChart.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import { loadPref, savePref } from '../../composables/prefs'
import LineChart, { type Series } from '../../components/ui/LineChart.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import BacktestPrice from './BacktestPrice.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { byFormat, money, num, pct, price, qty, shiftYears, today,
  trendClass } from '../../composables/format'

interface TradeRow {
  date: string
  side: string
  price: number
  shares: number
  amount: number
  fee: number
  reason: string
  pnl?: number
  ret?: number
  hold_days?: number
}

interface SummaryLabel {
  key: string
  label: string
  format: string
}

interface BacktestData {
  symbol: string
  rule: string
  begin: string
  end: string
  trades: TradeRow[]
  marks?: Mark[]
  bars?: Bar[]
  equity: { date: string; nav: number }[]
  summary: Record<string, number>
  summary_labels: SummaryLabel[]
  caliber: Record<string, unknown>
  warnings: string[]
}

const { data, loading, error, asOf, load } = useTool<BacktestData>('backtest')

const symbol = ref(loadPref('bt.symbol', '600519'))
const rule = ref<'ma_cross' | 'pe' | 'pb'>('ma_cross')
const fast = ref(loadPref('bt.fast', 5))
const slow = ref(loadPref('bt.slow', 20))
const buy = ref(loadPref('bt.buy', 20))
const sell = ref(loadPref('bt.sell', 40))
// begin/end 不持久化：默认是滚动两年窗，冻结成绝对日期会让窗口不随时间滚
const begin = ref(shiftYears(-2))
const end = ref(today())

function payload(): Record<string, unknown> {
  // 运行即落盘：以「用户上次运行过的」为准（自动跑是既有行为，持久化
  // 不新增请求时机）
  for (const [k, v] of Object.entries({ symbol: symbol.value,
    fast: fast.value, slow: slow.value, buy: buy.value,
    sell: sell.value })) {
    savePref(`bt.${k}`, v)
  }
  const base: Record<string, unknown> = {
    symbol: symbol.value, rule: rule.value,
    begin: begin.value, end: end.value,
  }
  if (rule.value === 'ma_cross') {
    base.fast = Number(fast.value)
    base.slow = Number(slow.value)
  } else {
    base.buy = Number(buy.value)
    base.sell = Number(sell.value)
  }
  return base
}

const kpis = computed<Kpi[]>(() => {
  const s = data.value?.summary ?? {}
  const labels = data.value?.summary_labels ?? []
  return labels.map((item) => ({
    key: item.key,
    label: item.label,
    value: byFormat(s[item.key], item.format),
    tone: item.key === 'max_drawdown' ? 'bad' : 'muted',
  }))
})

const equitySeries = computed<Series[]>(() => [{
  name: '净值',
  data: (data.value?.equity ?? []).map((p) => p.nav),
}])
const equityDates = computed(() =>
  (data.value?.equity ?? []).map((p) => p.date),
)

const tradeColumns: Column[] = [
  { key: 'date', label: '日期', mono: true, dim: true },
  { key: 'side', label: '方向' },
  { key: 'price', label: '价格', numeric: true },
  { key: 'shares', label: '股数', numeric: true },
  { key: 'amount', label: '金额', numeric: true },
  { key: 'fee', label: '费用', numeric: true, dim: true },
  { key: 'pnl', label: '本次盈亏', numeric: true },
  { key: 'reason', label: '原因', dim: true },
]

function asTrade(item: Record<string, unknown>): TradeRow {
  return item as unknown as TradeRow
}

onMounted(() => load(payload()))
</script>

<template>
  <PanelShell title="回测" subtitle="历史复现，不构成策略建议"
              :as-of="asOf" :loading="loading" @refresh="load(payload())">
    <template #actions>
      <span v-if="data" class="wb-chip">{{ data.symbol }} · {{ data.rule }}</span>
    </template>

    <div class="wb-bar">
      <label>
        标的
        <input v-model="symbol" class="wb-input w96" type="text" />
      </label>
      <label>
        规则
        <select v-model="rule" class="wb-input">
          <option value="ma_cross">均线交叉</option>
          <option value="pe">PE 阈值</option>
          <option value="pb">PB 阈值</option>
        </select>
      </label>
      <template v-if="rule === 'ma_cross'">
        <label>快线 <input v-model.number="fast" class="wb-input w64" type="number" /></label>
        <label>慢线 <input v-model.number="slow" class="wb-input w64" type="number" /></label>
      </template>
      <template v-else>
        <label>买点 <input v-model.number="buy" class="wb-input w72" type="number" /></label>
        <label>卖点 <input v-model.number="sell" class="wb-input w72" type="number" /></label>
      </template>
      <label>起 <input v-model="begin" class="wb-input w128" type="date" /></label>
      <label>止 <input v-model="end" class="wb-input w128" type="date" /></label>
      <button class="wb-btn" type="button" @click="load(payload())">运行</button>
    </div>

    <LoadingSkeleton v-if="loading" :rows="6" />

    <StateBlock v-else-if="error" kind="error" title="运行失败"
                :detail="error.message"
                hint="回测必须指定区间：不给区间会取全历史，单次可达数十万 EC。"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="load(payload())" />

    <template v-else>
      <KpiStrip :items="kpis" />

      <p v-for="w in data?.warnings ?? []" :key="w" class="wb-warn">{{ w }}</p>

      <BacktestPrice v-if="(data?.bars ?? []).length"
                     :bars="data?.bars ?? []" :marks="data?.marks ?? []"
                     :begin="data?.begin ?? ''" :end="data?.end ?? ''"
                     :page-as-of="asOf" />

      <div class="wb-card">
        <h2>净值曲线</h2>
        <LineChart v-if="equityDates.length" :series="equitySeries"
                   :x-labels="equityDates" area format="money" :height="240" />
        <p v-else class="wb-empty">无净值数据</p>
      </div>

      <div class="wb-card">
        <h2>成交明细（{{ data?.trades.length ?? 0 }} 笔）</h2>
        <DataTable :columns="tradeColumns"
                   :rows="(data?.trades ?? []) as unknown as Record<string, unknown>[]"
                   empty-text="区间内没有触发任何买卖点">
          <template #side="{ row }">
            <span :class="asTrade(row).side === 'buy' ? 'up' : 'down'">
              {{ asTrade(row).side === 'buy' ? '买入' : '卖出' }}
            </span>
          </template>
          <template #price="{ row }">{{ price(asTrade(row).price) }}</template>
          <template #shares="{ row }">{{ qty(asTrade(row).shares) }}</template>
          <template #amount="{ row }">{{ money(asTrade(row).amount) }}</template>
          <template #fee="{ row }">{{ num(asTrade(row).fee) }}</template>
          <template #pnl="{ row }">
            <span v-if="asTrade(row).pnl !== undefined"
                  :class="trendClass(asTrade(row).pnl)">
              {{ money(asTrade(row).pnl) }}（{{ pct(asTrade(row).ret) }}）
            </span>
            <span v-else class="dim">—</span>
          </template>
        </DataTable>
      </div>
    </template>
  </PanelShell>
</template>

<style scoped>
label {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-2);
}

.w64 {
  width: 56px;
}

.w72 {
  width: 64px;
}

.w96 {
  width: 88px;
}

.w128 {
  width: 132px;
}

h2 {
  margin: var(--wb-sp-5) 0 var(--wb-sp-4);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}
</style>
