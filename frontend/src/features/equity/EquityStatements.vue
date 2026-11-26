<script setup lang="ts">
/**
 * 财务报表（主要指标 / 利润表 / 资产负债表 / 现金流量表）—— 跨期透视表。
 *
 * **四张表全部走公开门面 `statements.*`，原生支持季报**（`period` 档位，
 * 累计口径 Q1..Q4）。表格结构是「科目一行、各期一列」（真实返回
 * `list[{cn,k,vals}]`），期次降序（最近一期在前）——与财务表的阅读习惯一致。
 */
import { computed } from 'vue'

import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import Segmented from '../../components/ui/Segmented.vue'
import { money, num, pct } from '../../composables/format'

export interface StatementRow {
  k: string
  /** 中文名：科目表用 `cn`，指标表用 `label` */
  cn?: string
  label?: string
  /** 口径（仅指标表给）：money/pct/num/days */
  format?: string
  /** 期次 → 值（真实返回的跨期列） */
  vals: Record<string, number | null>
}

const props = defineProps<{
  periods: string[]
  rows: StatementRow[]
  kind: string
  /** 报告期档位（年报/季报），由父级持有并随切换重发请求 */
  period?: 'annual' | 'quarter'
  loading?: boolean
}>()

const emit = defineEmits<{
  pick: [kind: 'indicators' | 'income' | 'balance' | 'cashflow']
  setPeriod: [period: 'annual' | 'quarter']
}>()

/**
 * 子页顺序：**主要指标最前**。
 *
 * 实务上看财报第一步是看营收/净利/ROE/毛利率/EPS，而不是直接翻 52 行
 * 科目明细。默认落在明细上等于让用户自己在几百个数字里找重点。
 */
const KINDS = [
  { key: 'indicators', label: '主要指标' },
  { key: 'income', label: '利润表' },
  { key: 'balance', label: '资产负债表' },
  { key: 'cashflow', label: '现金流量表' },
] as const

const columns = computed<Column[]>(() => [
  { key: 'cn', label: '科目' },
  ...props.periods.map((p) => ({ key: `p_${p}`, label: p, numeric: true })),
])

/** 子页选项与期次档位（Segmented 的 pick 值是 string|number，收窄回各自联合类型）。 */
const kindOptions = KINDS.map(({ key, label }) => ({ value: key, label }))

const PERIOD_OPTIONS = [
  { value: 'annual', label: '年报', title: '年报档：期次为年份' },
  { value: 'quarter', label: '季报',
    title: '季报累计档：期次为 YYYY-Qn（Q3 = 前三季）' },
] as const

function pickKind(value: string | number): void {
  emit('pick', value as 'indicators' | 'income' | 'balance' | 'cashflow')
}

function pickPeriod(value: string | number): void {
  emit('setPeriod', value as 'annual' | 'quarter')
}

/** 季报累计口径说明只在季报档显示（Q3 = 前三季，不是单季）。 */
const isQuarter = computed(() => props.period === 'quarter')

/** 把 `vals` 摊平成 `p_<期次>` 键，供 DataTable 直接取值。 */
const flatRows = computed<Record<string, unknown>[]>(() =>
  props.rows.map((row) => {
    const flat: Record<string, unknown> = { cn: row.label ?? row.cn ?? row.k }
    // 口径随行下传：金额按亿/万、比率按百分比、天数带单位
    flat.__format = row.format ?? 'money'
    for (const [period, value] of Object.entries(row.vals ?? {})) {
      flat[`p_${period}`] = value
    }
    return flat
  }),
)

/** 按行口径渲染一个值。 */
function cell(value: unknown, format: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (format === 'pct') return pct(value)
  if (format === 'days') return `${num(value, 1)} 天`
  if (format === 'num') return num(value)
  return money(value)
}

const currentLabel = computed(
  () => KINDS.find((k) => k.key === props.kind)?.label ?? props.kind,
)
</script>

<template>
  <div>
    <div class="subbar">
      <Segmented :options="kindOptions" :selected="kind" @pick="pickKind" />
      <span class="gap" />
      <Segmented :options="PERIOD_OPTIONS" :selected="period"
                 @pick="pickPeriod" />
    </div>

    <h2 class="wb-h2">
      {{ currentLabel }}（{{ rows.length }}
      {{ kind === 'indicators' ? '项' : '个科目' }} · {{ periods.length }} 期）
      <!-- 年份期次是这张表诚实的「数据期」，措辞用「报告期」不用「截至」 -->
      <span v-if="periods.length" class="wb-chip">最新报告期 {{ periods[0] }}</span>
    </h2>
    <p v-if="isQuarter" class="wb-hint">
      季报为累计口径（Q1=一季报、Q2=半年报、Q3=前三季、Q4 与年报同源），
      不是单季值。
    </p>
    <DataTable :columns="columns" :rows="flatRows"
               :empty-text="`${currentLabel}无科目数据`">
      <template v-for="p in periods" :key="p" #[`p_${p}`]="{ row, value }">
        {{ cell(value, (row as Record<string, unknown>).__format) }}
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
.subbar {
  display: flex;
  gap: var(--wb-sp-2);
  margin-bottom: var(--wb-sp-4);
  flex-wrap: wrap;
}

.gap {
  flex: 1;
}
</style>
