<script setup lang="ts">
/**
 * 自选（`/api/watchlist/run`）。
 *
 * 后端保证「无论多少标的，两次请求（快照+日期伴取）」——页面如实显示
 * （`请求 1 次`），因为用户无从验证，而这是他关心的事。
 *
 * **增删是本地写入、零取数**。此前后端 `store.add_watch/remove_watch` 已实现
 * 却无任何调用方，用户只能看到 5 只示例票——清单表形同虚设。
 */
import { computed, onMounted, ref } from 'vue'

import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'
import { loadPref, savePref } from '../../composables/prefs'
import { money, pct, price, trendClass } from '../../composables/format'

interface QuoteRow {
  symbol: string
  name: string
  close: number | null
  percent: number | null
  chg_5d: number | null
  chg_20d: number | null
  vol_ratio_5: number | null
  amount: number | null
  mv: number | null
  /** 本行数据自己的截止日（停牌票停在停牌前） */
  kline_date?: string | null
  missing?: boolean
  /** 现价来自盘中快照（live=true 请求时） */
  live?: boolean
}

interface WatchData {
  symbols: string[]
  rows: QuoteRow[]
  columns: { key: string; label: string }[]
  count: number
  request_count: number
  groups: string[]
  /** add/remove 的回显：真实落库的代码（证明写进去了） */
  saved?: string[]
}

const { data, loading, error, asOf, load } = useTool<WatchData>('watchlist')
const input = ref('')
const sortKey = ref<'percent' | 'amount' | 'mv'>('percent')
const sortDesc = ref(true)
/** 增删后的本地提示（不占用全局 error / data 状态）。 */
const savedNote = ref('')

const columns: Column[] = [
  { key: 'symbol', label: '代码', mono: true, dim: true },
  { key: 'name', label: '名称' },
  { key: 'close', label: '最新价', numeric: true },
  { key: 'percent', label: '涨跌幅', numeric: true },
  { key: 'chg_5d', label: '5 日', numeric: true },
  { key: 'chg_20d', label: '20 日', numeric: true },
  { key: 'vol_ratio_5', label: '量比', numeric: true },
  { key: 'amount', label: '成交额', numeric: true },
  // 行级数据截止日：页顶「截至」是全页最大值，某行停在旧日期即停牌/缺数
  { key: 'kline_date', label: '数据日期', mono: true, dim: true },
]

/** 排序用**原始数值**，不用格式化后的字符串（`+10%` 与 `+9%` 的字符串序是错的）。 */
const rows = computed(() => {
  const list = [...(data.value?.rows ?? [])]
  const key = sortKey.value
  list.sort((a, b) => {
    const av = a[key] ?? -Infinity
    const bv = b[key] ?? -Infinity
    return sortDesc.value ? bv - av : av - bv
  })
  return list as unknown as Record<string, unknown>[]
})

function asQuote(item: Record<string, unknown>): QuoteRow {
  return item as unknown as QuoteRow
}

function toggleSort(key: 'percent' | 'amount' | 'mv'): void {
  if (sortKey.value === key) sortDesc.value = !sortDesc.value
  else {
    sortKey.value = key
    sortDesc.value = true
  }
}

/** 盘中实时：live_many 本就是盘中日K，开启后现价/涨跌幅以它为准。 */
const live = ref(loadPref('watch.live', false))

function quotesBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { live: live.value, ...extra }
}

function toggleLive(): void {
  live.value = !live.value
  savePref('watch.live', live.value)
  load(quotesBody())
}

function submit(): void {
  const text = input.value.trim()
  load(quotesBody(text ? { symbols: text } : {}))
}

/** 写入自选（零取数）。写入后**重新拉一次行情**让表立刻反映新清单。 */
function mutate(action: 'add' | 'remove'): void {
  const text = input.value.trim()
  if (!text) {
    savedNote.value = '请先在上方输入代码'
    return
  }
  savedNote.value = ''
  load({ action, symbols: text })
    .then(() => {
      const saved = data.value?.saved ?? []
      const verb = action === 'add' ? '已加入' : '已移出'
      savedNote.value = `${verb} ${text}（本组现有 ${saved.length} 只）`
      // 写入成功后刷新行情表；**不带 action**，走默认 quotes
      return load(quotesBody())
    })
    .catch(() => {
      savedNote.value = ''
    })
}

onMounted(() => load(quotesBody()))
</script>

<template>
  <PanelShell title="自选" subtitle="批量快照 + 日期伴取：2 次请求覆盖全部标的"
              :as-of="asOf" :loading="loading" @refresh="load(quotesBody())">
    <template #actions>
      <span v-if="data" class="wb-chip">请求 {{ data.request_count }} 次</span>
    </template>

    <div class="wb-bar">
      <input v-model="input" class="wb-input" type="text"
             placeholder="代码用逗号分隔，如 600519,000001（留空读本地自选）"
             @keyup.enter="submit" />
      <button class="wb-btn" type="button" @click="submit">加载</button>
      <button class="wb-btn" type="button" @click="mutate('add')">加入自选</button>
      <button class="wb-btn" type="button" @click="mutate('remove')">移出自选</button>
      <span class="spacer" />
      <button class="wb-tab" :class="{ on: live }" type="button"
              title="开启后现价/涨跌幅/额/市值以盘中快照（live_many）为准；休市时即最近收盘价"
              @click="toggleLive">
        实时{{ live ? ' ·开' : '' }}
      </button>
      <button class="wb-tab" :class="{ on: sortKey === 'percent' }" type="button"
              @click="toggleSort('percent')">
        按涨跌幅{{ sortKey === 'percent' ? (sortDesc ? '↓' : '↑') : '' }}
      </button>
      <button class="wb-tab" :class="{ on: sortKey === 'amount' }" type="button"
              @click="toggleSort('amount')">
        按成交额{{ sortKey === 'amount' ? (sortDesc ? '↓' : '↑') : '' }}
      </button>
    </div>

    <p v-if="savedNote" class="note ok">{{ savedNote }}</p>

    <LoadingSkeleton v-if="loading" :rows="6" />

    <StateBlock v-else-if="error" kind="error" title="读取失败" :detail="error.message"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="load({})" />

    <DataTable v-else :columns="columns" :rows="rows"
               empty-text="自选清单为空——在上面输入代码后点「加入自选」">
      <template #symbol="{ row }">
        <a class="rowlink" :href="`#/equity?sym=${asQuote(row).symbol}`"
           :title="`查看 ${asQuote(row).name} 的基本面`">
          {{ asQuote(row).symbol }}
        </a>
        <span v-if="asQuote(row).live" class="lv"
              title="现价来自盘中快照接口（休市时即最近收盘价）">实时</span>
      </template>
      <template #close="{ value }">{{ price(value as number) }}</template>
      <template #percent="{ row }">
        <span :class="trendClass(asQuote(row).percent)">{{ pct(asQuote(row).percent) }}</span>
      </template>
      <template #chg_5d="{ row }">
        <span :class="trendClass(asQuote(row).chg_5d)">{{ pct(asQuote(row).chg_5d) }}</span>
      </template>
      <template #chg_20d="{ row }">
        <span :class="trendClass(asQuote(row).chg_20d)">{{ pct(asQuote(row).chg_20d) }}</span>
      </template>
      <template #vol_ratio_5="{ value }">
        {{ value === null ? '—' : Number(value).toFixed(2) }}
      </template>
      <template #amount="{ row }">{{ money(asQuote(row).amount) }}</template>
      <template #kline_date="{ row }">{{ asQuote(row).kline_date || '—' }}</template>
    </DataTable>
  </PanelShell>
</template>

<style scoped>
.input:focus {
  outline: 1px solid var(--wb-accent);
}

.btn:hover {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}

.spacer {
  flex: 1;
}

.tab.on {
  color: var(--wb-accent);
  border-color: var(--wb-border-med);
  background: var(--wb-accent-bg);
}

.note {
  margin: 0;
  padding: var(--wb-sp-2) var(--wb-sp-6);
  font-size: var(--wb-fs-2);
}

.note.ok {
  color: var(--wb-down);
}

/* 行内「实时」小标：现价来自盘中快照接口 */
.lv {
  margin-left: var(--wb-sp-2);
  font-size: var(--wb-fs-1);
  color: var(--wb-accent);
}

/* 行内代码 → 个股研究的跳转链接（等宽与表格一致，hover 提亮） */
.rowlink {
  color: var(--wb-accent);
  text-decoration: none;
  font-family: var(--wb-font-mono);
}

.rowlink:hover {
  text-decoration: underline;
}
</style>
