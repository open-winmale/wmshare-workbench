<script setup lang="ts">
/**
 * 个股研究（`/api/equity/run`）：**分区懒加载**。
 *
 * 打开只拉「概览」，其余分区点开才取。高成本分区（`decomp`）需要二次确认，
 * 后端会先返回确认请求而**不发任何上游调用**。
 *
 * 本文件只做「壳 + 取数编排」：标的输入、分区页签、确认流程。各分区的
 * 渲染在 `EquityBody`，数据形状不在这里认识——否则每加一个分区这里就长一截。
 */
import { computed, onMounted, ref } from 'vue'

import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import Segmented from '../../components/ui/Segmented.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { loadPref, savePref } from '../../composables/prefs'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import EquityBody, { type SectionData } from './EquityBody.vue'
import type { DecompData } from './EquityDecomp.vue'

interface Section {
  key: string
  title: string
  note: string
  expensive: boolean
}

interface EquityData {
  symbol: string
  section: string
  sections: Section[]
  data?: SectionData & {
    /** 拆解分区（结构独立） */
    ok?: boolean
    reason?: string
    years?: number
    span_years?: number | null
    start_date?: string
    end_date?: string
    summary?: DecompData['summary']
    attribution?: DecompData['attribution']
    yearly?: DecompData['yearly']
    monthly?: DecompData['monthly']
  }
}

const { data, loading, error, asOf, load } = useTool<EquityData>('equity')
const symbol = ref('600519')
const section = ref('overview')
const domain = ref<'indicators' | 'income' | 'balance' | 'cashflow'>('indicators')
/** 报表期档：年报 / 季报（季报为累计口径 Q1..Q4，后端透传给 statements 门面） */
const stmtPeriod = ref<'annual' | 'quarter'>('annual')

/** 拆解分区：把扁平字段收成组件要的形状。 */
const decomp = computed<DecompData | null>(() => {
  if (data.value?.section !== 'decomp') return null
  const d = data.value.data
  if (!d) return null
  return {
    ok: d.ok !== false,
    reason: d.reason,
    years: d.years ?? 5,
    symbol: data.value.symbol,
    span_years: d.span_years ?? null,
    start_date: d.start_date,
    end_date: d.end_date,
    summary: d.summary,
    attribution: d.attribution,
    yearly: d.yearly,
    monthly: d.monthly,
  }
})

function go(next: string, confirmed = false, force = false): void {
  section.value = next
  savePref('equity.section', next)
  const body: Record<string, unknown> = { symbol: symbol.value, section: next }
  if (next === 'statements') {
    body.domain = domain.value
    body.period = stmtPeriod.value
  }
  // 拆解年限每次都要带：年限是请求参数，不带就会按后端默认值执行
  if (next === 'decomp') body.years = decompYears.value
  if (next === 'bars') body.days = barDays.value
  if (confirmed) body.confirmed = true
  // 刷新按钮透传 force：分时/现价这类「用户要此刻数据」的面绕过 30s
  // 缓存直取上游（后端只对 live/分时生效，慢变档案仍走缓存）
  if (force) body.force = true
  load(body)
}

function pickStatement(
  next: 'indicators' | 'income' | 'balance' | 'cashflow',
): void {
  domain.value = next
  savePref('equity.domain', next)
  section.value = 'statements'
  load({ symbol: symbol.value, section: 'statements', domain: next,
         period: stmtPeriod.value })
}

/** 年报/季报切换：换档等于换请求（期次键完全不同），重发。 */
function pickStmtPeriod(period: 'annual' | 'quarter'): void {
  stmtPeriod.value = period
  savePref('equity.stmtPeriod', period)
  load({ symbol: symbol.value, section: 'statements', domain: domain.value,
         period })
}

/** 拆解年限：上游只接受 3/5/10；**成本随年限超线性增长**。 */
const DECOMP_YEARS = [
  { value: 3, label: '3 年' },
  { value: 5, label: '5 年' },
  { value: 10, label: '10 年（最贵）' },
] as const

const decompYears = ref<number>(5)

/** Segmented 的 pick 值是 string|number（选项可为枚举字符串或数字档位）。 */
function pickYears(years: string | number): void {
  decompYears.value = Number(years)
  savePref('equity.decompYears', Number(years))
  // 改年限等于换一个请求：必须重新走确认（成本可能差几十倍）
  load({ symbol: symbol.value, section: 'decomp', years: Number(years) })
}

/** 行情走势的交易日窗口（后端钳 20–500；`limit` 是「最近 N 个交易日」）。 */
const BAR_DAYS = [
  { value: 60, label: '60 日' },
  { value: 120, label: '120 日' },
  { value: 250, label: '250 日' },
  { value: 500, label: '500 日' },
] as const

const barDays = ref<number>(120)

function pickBarDays(days: string | number): void {
  barDays.value = Number(days)
  savePref('equity.barDays', Number(days))
  load({ symbol: symbol.value, section: 'bars', days: Number(days) })
}

function submit(force = false): void {
  savePref('equity.symbol', symbol.value)
  go(section.value, false, force)
}

onMounted(() => {
  // 支持从其它页跳转进来：#/equity?sym=000001（自选/行情行的链接）；
  // 深链优先，没有深链时恢复上次的选择（P5-01 轻量持久化）
  const query = window.location.hash.split('?')[1]
  const sym = new URLSearchParams(query ?? '').get('sym')
  symbol.value = sym ?? loadPref('equity.symbol', symbol.value)
  if (sym) savePref('equity.symbol', sym)
  section.value = loadPref('equity.section', section.value)
  domain.value = loadPref('equity.domain', domain.value)
  stmtPeriod.value = loadPref('equity.stmtPeriod', stmtPeriod.value)
  decompYears.value = loadPref('equity.decompYears', decompYears.value)
  barDays.value = loadPref('equity.barDays', barDays.value)
  go(section.value)
})
</script>

<template>
  <PanelShell title="个股研究" subtitle="分区懒加载：打开只取概览；本页不产出投资结论"
              :as-of="asOf" :loading="loading" @refresh="submit(true)">
    <template #actions>
      <input v-model="symbol" class="wb-input w96" type="text"
             @keyup.enter="submit()" />
      <button class="wb-btn" type="button" @click="submit()">载入</button>
    </template>

    <div class="tabs">
      <button v-for="s in data?.sections ?? []" :key="s.key" class="wb-tab"
              :class="{ on: section === s.key, expensive: s.expensive }"
              type="button" :title="s.note" @click="go(s.key)">
        {{ s.title }}<span v-if="s.expensive" class="star">*</span>
      </button>
    </div>

    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock v-else-if="error" kind="error" title="读取失败" :detail="error.message"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="submit()" />

    <div v-else class="body">
      <!-- 年限选择器：改年限会重发请求，所以要能看见当前选的是哪档 -->
      <div v-if="section === 'decomp'" class="subbar">
        <span class="pickLabel">持有年限</span>
        <Segmented :options="DECOMP_YEARS" :selected="decompYears"
                   @pick="pickYears" />
      </div>

      <!-- 行情走势的区间选择：同样要能看见当前选的是哪档 -->
      <div v-else-if="section === 'bars'" class="subbar">
        <span class="pickLabel">区间</span>
        <Segmented :options="BAR_DAYS" :selected="barDays" @pick="pickBarDays" />
      </div>

      <EquityBody :symbol="data?.symbol ?? symbol" :section="data?.section ?? section"
                  :data="data?.data" :decomp="decomp" :domain="domain"
                  :stmt-period="stmtPeriod"
                  @pick-statement="pickStatement" @set-period="pickStmtPeriod" />
    </div>
  </PanelShell>
</template>

<style scoped>
.w96 {
  width: 88px;
}

.tabs {
  display: flex;
  gap: var(--wb-sp-2);
  padding: var(--wb-sp-3) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
  flex-wrap: wrap;
}

.tab.expensive {
  color: var(--wb-warning);
}

.star {
  color: var(--wb-warning);
}

.body {
  padding: var(--wb-sp-6);
}

.subbar {
  display: flex;
  gap: var(--wb-sp-2);
  margin-bottom: var(--wb-sp-4);
  flex-wrap: wrap;
}

.pickLabel {
  align-self: center;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}
</style>
