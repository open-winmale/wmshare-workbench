<script setup lang="ts">
/**
 * 数据源与新鲜度总览（`/api/sources/run`，零取数）。
 *
 * 这页的价值在于**把 119 个数据集的过期状态摊开**——它回答的不是
 * 「有哪些数据」，而是「我看到的这份数据有多旧」。
 */
import { computed, onMounted, ref } from 'vue'

import { ApiError, run } from '../../api/client'
import DataTable, { type Column } from '../../components/ui/DataTable.vue'
import KpiStrip, { type Kpi } from '../../components/ui/KpiStrip.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import StatusBadge from '../../components/ui/StatusBadge.vue'
import { formatTtl, stateLabel } from './format'
import type { Dataset, SourcesData } from './types'

const data = ref<SourcesData | null>(null)
const loading = ref(true)
const error = ref<{ message: string; action: string } | null>(null)
const onlyProblems = ref(true)

/** 119 行全铺出来没人看得完；默认只看问题项。 */
const rows = computed<Record<string, unknown>[]>(() => {
  const all = data.value?.datasets ?? []
  const picked = onlyProblems.value
    ? all.filter((d) => d.freshness === 'expired' || d.freshness === 'stale')
    : all
  return picked as unknown as Record<string, unknown>[]
})

const columns: Column[] = [
  { key: 'label', label: '数据集' },
  { key: 'collection', label: '集合', mono: true, dim: true },
  { key: 'stale_after_days', label: '预警', numeric: true },
  { key: 'expire_after_days', label: '过期', numeric: true },
  { key: 'ttl_s', label: 'TTL', numeric: true, dim: true },
  { key: 'freshness', label: '状态' },
]

const kpis = computed<Kpi[]>(() => {
  const s = data.value?.summary ?? { fresh: 0, stale: 0, expired: 0, unknown: 0 }
  return [
    { key: 'fresh', label: '健康', value: s.fresh, tone: 'ok' },
    { key: 'stale', label: '预警', value: s.stale, tone: 'warn' },
    { key: 'expired', label: '已过期', value: s.expired, tone: 'bad' },
    { key: 'unknown', label: '未知', value: s.unknown, tone: 'muted' },
  ]
})

const actionLabel: Record<string, string> = {
  retry: '重试',
  topup: '去充值',
  config: '去配置',
  fix_input: '修改输入',
  report: '报告问题',
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const env = await run<SourcesData>('sources', {})
    data.value = env.data
  } catch (exc) {
    error.value = exc instanceof ApiError
      ? { message: exc.message, action: exc.action }
      : { message: exc instanceof Error ? exc.message : String(exc), action: 'report' }
  } finally {
    loading.value = false
  }
}

function ds(row: Record<string, unknown>): Dataset {
  return row as unknown as Dataset
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <header class="head">
      <h1>数据源与新鲜度</h1>
      <p class="sub">
        共 <b>{{ data?.count ?? '—' }}</b> 个受监控数据集 · 阈值来自平台
        <code>stats_config</code>（<b>{{ data?.available ? '已加载' : '不可用' }}</b>）
      </p>
      <button class="wb-btn" type="button" :disabled="loading" @click="load">
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </header>

    <LoadingSkeleton v-if="loading" :rows="5" />

    <StateBlock
      v-else-if="error"
      kind="error"
      title="读取失败"
      :detail="error.message"
      hint="这通常意味着后端未启动，或数据库文件不可读。"
      :action-label="actionLabel[error.action] ?? '重试'"
      @action="load"
    />

    <StateBlock
      v-else-if="!data?.available"
      kind="empty"
      title="新鲜度阈值不可用"
      :detail="data?.note"
      hint="设置环境变量 WORKBENCH_STATS_CONFIG 指向 stats_config.py 即可启用。在此之前本页不显示任何过期判断——不知道就不猜。"
    />

    <template v-else>
      <KpiStrip :items="kpis" />

      <!-- age_days 是相对数：把判定所用的参照日如实给出，用户才能校验 -->
      <p v-if="data?.reference" class="ref">
        新鲜度相对 <b>{{ data.reference }}</b> 计算。
      </p>

      <div class="filters">
        <button class="wb-tab" :class="{ on: onlyProblems }" type="button"
                @click="onlyProblems = true">
          仅问题项（{{ data.summary.stale + data.summary.expired }}）
        </button>
        <button class="wb-tab" :class="{ on: !onlyProblems }" type="button"
                @click="onlyProblems = false">
          全部（{{ data.count }}）
        </button>
        <span class="spacer" />
        <span class="meta">
          库 v{{ data.store.version }} · {{ data.store.tables }} 表 · 凭证
          {{ data.credentials.configured ? '已配置' : '未配置' }}<template
            v-if="data.credentials.configured">（{{ data.credentials.source }}）</template>
        </span>
      </div>

      <DataTable :columns="columns" :rows="rows"
                 empty-text="没有过期或预警的数据集——所有数据都在阈值内。">
        <template #stale_after_days="{ value }">{{ value }} 天</template>
        <template #expire_after_days="{ value }">{{ value }} 天</template>
        <template #ttl_s="{ value }">{{ formatTtl(Number(value)) }}</template>
        <template #freshness="{ row }">
          <StatusBadge :tone="ds(row).freshness" :text="stateLabel(ds(row).freshness)" />
          <span v-if="ds(row).warning" class="warn-text">{{ ds(row).warning }}</span>
        </template>
      </DataTable>
    </template>
  </section>
</template>

<style scoped>
.panel {
  background: var(--wb-bg-surface);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-3);
  overflow: hidden;
}

.head {
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-5);
  padding: var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

h1 {
  margin: 0;
  font-size: var(--wb-fs-6);
  font-weight: 500;
}

.sub {
  margin: 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.btn:hover:not(:disabled) {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}

.btn:disabled {
  opacity: 0.5;
}

code {
  background: var(--wb-bg-raised);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-1);
  padding: 0 var(--wb-sp-2);
}

.filters {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-2);
  padding: var(--wb-sp-4) var(--wb-sp-6);
  border-bottom: 1px solid var(--wb-border-dim);
}

.ref {
  margin: 0;
  padding: var(--wb-sp-2) var(--wb-sp-6) 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.tab.on {
  color: var(--wb-accent);
  border-color: var(--wb-border-med);
  background: var(--wb-accent-bg);
}

.spacer {
  flex: 1;
}

.meta {
  font-size: var(--wb-fs-1);
  color: var(--wb-text-dim);
}

.warn-text {
  margin-left: var(--wb-sp-4);
  color: var(--wb-text-tertiary);
}
</style>
