<script setup lang="ts">
/**
 * 宏观（`/api/economics/run`）：宏观时序、国债曲线、汇率。
 *
 * 三块各自独立容错——任一块失败不影响其它两块。
 */
import { computed, onMounted, ref } from 'vue'

import AsOfChip from '../../components/ui/AsOfChip.vue'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import LineChart, { type Series } from '../../components/ui/LineChart.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import Segmented from '../../components/ui/Segmented.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { num } from '../../composables/format'
import { loadPref, savePref } from '../../composables/prefs'

interface Point {
  sas: string
  value: number | null
}

interface CurvePoint {
  tenor: string
  yield: number
}

interface FxRow {
  ccy: string
  date: string
  middle: number | null
}

interface CodeOption {
  code: string
  label: string
}

interface EconData {
  code: string
  codes: CodeOption[]
  series: Point[]
  series_note: string
  curve: CurvePoint[]
  curve_note: string
  fx: FxRow[]
  fx_note: string
  tenors: string[]
  curve_name: string
}

const { data, loading, error, asOf, warnings, load } =
  useTool<EconData>('economics')
const selected = ref(loadPref('econ.code', '$CPI'))

const seriesLabels = computed(() => (data.value?.series ?? []).map((p) => p.sas))
const seriesData = computed<Series[]>(() => [{
  name: data.value?.code ?? '序列',
  data: (data.value?.series ?? []).map((p) => p.value),
}])

const curveLabels = computed(() => (data.value?.curve ?? []).map((p) => p.tenor))
const curveData = computed<Series[]>(() => [{
  name: '国债收益率',
  data: (data.value?.curve ?? []).map((p) => p.yield),
}])

const fxColumns: Column[] = [
  { key: 'ccy', label: '币种', mono: true },
  { key: 'date', label: '日期', dim: true },
  { key: 'middle', label: '中间价', numeric: true },
]

/** 指数切换选项（Segmented 的 pick 值是 string|number，收窄回字符串码）。 */
const codeOptions = computed(() =>
  (data.value?.codes ?? []).map((c) => ({
    value: c.code, label: c.label, title: c.label,
  })))

function pick(code: string | number): void {
  selected.value = String(code)
  savePref('econ.code', String(code))
  load({ code: String(code) })
}

onMounted(() => load({ code: selected.value }))
</script>

<template>
  <PanelShell title="宏观" subtitle="宏观时序 · 国债收益率曲线 · 汇率中间价"
              :as-of="asOf" :loading="loading" @refresh="load({ code: selected })">
    <template #actions>
      <!-- series_note 是宏观块自己的「最新期」，不是全页截止——挪进卡片头 -->
    </template>

    <div class="wb-bar">
      <Segmented :options="codeOptions" :selected="selected" @pick="pick" />
    </div>

    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock v-else-if="error" kind="error" title="读取失败" :detail="error.message"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="load({ code: selected })" />

    <template v-else>
      <p v-for="w in warnings" :key="w" class="wb-warn">{{ w }}</p>

      <div class="grid">
        <div class="wb-card">
          <h2 class="card-head">
            {{ data?.code }} 时序
            <span v-if="data?.series_note" class="wb-chip"
                  title="宏观指标的最新期次（月频期点，非日期）">
              {{ data.series_note }}
            </span>
          </h2>
          <LineChart v-if="seriesData[0].data.length" :series="seriesData"
                     :x-labels="seriesLabels" area :height="230" />
          <p v-else class="wb-empty">{{ data?.series_note || '无可用序列' }}</p>
        </div>

        <div class="wb-card">
          <h2 class="card-head">
            {{ data?.curve_name || '国债收益率曲线' }}
            <AsOfChip />
          </h2>
          <p class="wb-hint">{{ data?.curve_note }}</p>
          <LineChart v-if="curveData[0].data.length" :series="curveData"
                     :x-labels="curveLabels" format="pct" :height="210" />
          <p v-else class="wb-empty">无可用期限</p>
        </div>
      </div>

      <div class="wb-card wide">
        <h2>汇率中间价（{{ data?.fx_note }}）</h2>
        <DataTable :columns="fxColumns"
                   :rows="(data?.fx ?? []) as unknown as Record<string, unknown>[]"
                   empty-text="无在库币种">
          <template #middle="{ value }">{{ num(value as number, 4) }}</template>
        </DataTable>
      </div>
    </template>
  </PanelShell>
</template>

<style scoped>
.tab.on {
  color: var(--wb-accent);
  border-color: var(--wb-border-med);
  background: var(--wb-accent-bg);
}

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
  margin: 0 0 var(--wb-sp-3);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.card-head {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-3);
}
</style>
