<script setup lang="ts">
/**
 * 选股（`/api/screener/run`）：条件选股 + 策略库。
 *
 * 四件事在 UI 上必须做对：
 *
 * 1. **表达式错误本地化提示**：写 `and` 会被拦，提示该用 `&&`。
 * 2. **超预算要求二次确认**：显示预估 EC 与「确认后才会发请求」，
 *    而不是先跑再告诉用户花了多少。
 * 3. **策略可存可重跑**：存表达式原文，点名字回填。
 * 4. **排除负值默认开**：亏损股的负 PE 会把「低估值」变成「亏得最狠」，
 *    后端按 where/order 引用的指标追加 `> 0`（服务端守卫，省 EC）；
 *    追加了什么会在告警里如实写出，可关。
 */
import { computed, onMounted, ref } from 'vue'

import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { loadPref, savePref } from '../../composables/prefs'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { num } from '../../composables/format'
import ScreenerLists, { type Preset, type SavedScreen } from './ScreenerLists.vue'
import { BOOL_COLUMNS, COLUMN_LABELS, PERCENT_COLUMNS } from './labels'

interface Estimate {
  pred_lo: number | null
  pred_hi: number | null
  model: string
}

interface ScreenerData {
  needs_confirm?: boolean
  where: string
  total?: number | null
  rows?: Record<string, unknown>[]
  estimate: Estimate
  presets: Preset[]
  saved: SavedScreen[]
  saved_as?: string
  message?: string
  threshold?: number
}

const { data, loading, error, asOf, warnings, load } = useTool<ScreenerData>('screener')
const where = ref(loadPref('screener.where', '$PE_TTM < 15'))
const limit = ref(50)
const saveAs = ref('')
const excludeNeg = ref<boolean>(loadPref('screener.exclude_negative', true))

/** 显示列：用后端返回的行键，但表头换成人能读的名字。 */
const columns = computed<Column[]>(() => {
  const rows = data.value?.rows ?? []
  const keys = rows.length ? Object.keys(rows[0]) : []
  return keys.map((key) => ({
    key,
    // 表头显示中文名而不是 `$PE_TTM`——指标码是接口细节
    label: COLUMN_LABELS[key] ?? key,
    numeric: rows.some((r) => typeof r[key] === 'number'),
    mono: key.length <= 8,
    dim: key === 'symbol',
  }))
})

const tableRows = computed(() =>
  (data.value?.rows ?? []) as unknown as Record<string, unknown>[],
)

function run(confirmed = false): void {
  savePref('screener.where', where.value)
  savePref('screener.exclude_negative', excludeNeg.value)
  const body: Record<string, unknown> = {
    where: where.value,
    limit: limit.value,
    exclude_negative: excludeNeg.value,
  }
  if (confirmed) body.confirmed = true
  if (saveAs.value.trim()) body.save_as = saveAs.value.trim()
  load(body)
}

/** 预设与已存策略的回填动作相同：回填表达式原文后立即重跑。 */
function usePreset(expr: string): void {
  where.value = expr
  run()
}

function asNum(value: unknown): string {
  return typeof value === 'number' ? num(value) : String(value ?? '—')
}

/** 列展示：布尔→是/否，比率→百分数，其余按数值格式化。 */
function display(value: unknown, key: string): string {
  if (BOOL_COLUMNS.has(key)) return value ? '是' : '否'
  if (PERCENT_COLUMNS.has(key) && typeof value === 'number') {
    return `${num(value * 100)}%`
  }
  return asNum(value)
}

onMounted(() => run())
</script>

<template>
  <PanelShell title="选股" subtitle="表达式原文可保存，重跑按当前数据重新求值"
              :as-of="asOf" :loading="loading" @refresh="run()">
    <template #actions>
      <span v-if="data?.estimate?.pred_hi" class="wb-chip">
        预估 ≤ {{ data.estimate.pred_hi.toLocaleString() }} EC
      </span>
      <!-- 选股结果集上游不带日期：整页一致地「无日期」，按收敛规则页头一个 -->
      <span v-else-if="!asOf && data?.rows?.length" class="wb-chip"
            title="上游接口未提供结果集的数据截止日期">截至未知</span>
    </template>

    <div class="wb-bar">
      <textarea v-model="where" class="wb-input grow expr" rows="2"
                placeholder='表达式，如 $PE_TTM < 15（用 && / || / !，不要用 and/or/not）'
                @keydown.enter.exact.prevent="run()" />
      <label>
        上限
        <input v-model.number="limit" class="wb-input w72" type="number" />
      </label>
      <label class="chk" title="布尔标志位跳过；商誉/有息负债等零值合法只排除负值；后端会如实披露追加了什么">
        <input v-model="excludeNeg" type="checkbox" /> 排除负值
      </label>
      <input v-model="saveAs" class="wb-input w128" type="text"
             placeholder="策略名（可选）" />
      <button class="wb-btn" type="button" @click="run()">查询</button>
    </div>

    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock v-else-if="error" kind="error" title="查询失败"
                :detail="error.message"
                hint="表达式里不要用 and/or/not；请改用 && / || / !。"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="run()" />

    <StateBlock v-else-if="data?.needs_confirm" kind="empty"
                title="需要确认后才发起请求"
                :detail="data.message"
                :hint="`阈值 ${(data.threshold ?? 0).toLocaleString()} EC；当前零请求。`"
                action-label="确认并运行"
                @action="run(true)" />

    <template v-else>
      <ScreenerLists :presets="data?.presets ?? []"
                     :saved="data?.saved ?? []" @use="usePreset" />

      <p v-for="w in warnings" :key="w" class="wb-warn">{{ w }}</p>

      <div class="result">
        <h2>
          命中 {{ data?.total ?? data?.rows?.length ?? 0 }} 只
          <span v-if="data?.saved_as" class="ok">· 已保存为「{{ data.saved_as }}」</span>
        </h2>
        <DataTable :columns="columns" :rows="tableRows"
                   empty-text="没有标的命中这个表达式">
          <template v-for="c in columns" #[c.key]="{ value }" :key="c.key">
            <span v-if="c.numeric">{{ display(value, c.key) }}</span>
            <template v-else>{{ display(value, c.key) }}</template>
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

.grow {
  flex: 1 1 320px;
  min-width: 200px;
}

.expr {
  min-height: 44px;
  resize: vertical;
  line-height: 1.4;
  padding-top: var(--wb-sp-2);
  padding-bottom: var(--wb-sp-2);
}

.w72 {
  width: 64px;
}

.w128 {
  width: 140px;
}

.btn:hover {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}

.result {
  padding: var(--wb-sp-5) var(--wb-sp-6) var(--wb-sp-6);
  min-width: 0;
}

.ok {
  color: var(--wb-down);
  font-weight: 400;
}
</style>
