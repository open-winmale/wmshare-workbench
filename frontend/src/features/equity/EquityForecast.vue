<script setup lang="ts">
/**
 * 业绩预告分区：预告 / 快报 / 下次预约披露 三块。
 *
 * **三块都要显示**，包括空块。只渲染有数据的那块会让用户以为「这页只有
 * 快报」，而实际上这家公司根本没发过预告——「没发」和「没显示」是
 * 两件完全不同的事。
 *
 * 字段的 0 已在后端归成 `null`（上游用 0 表示「没披露」），这里只需把
 * `null` 渲染成「—」。**不要在这里把 `null` 当 0 显示**：那会凭空造出
 * 「预计净利润 0 元 ～ 0 元」这样一条上游从未给出的事实。
 */
import StateBlock from '../../components/ui/StateBlock.vue'
import { money, num, pct } from '../../composables/format'

export interface ForecastField {
  key: string
  label: string
  value: string | number | null
  /** `money` 元 · `pct` 小数 · `num` 两位小数 · `int` 计数 · `text` 原样 */
  format: string
}

export interface ForecastBlock {
  key: string
  title: string
  fields: ForecastField[]
  empty: boolean
}

defineProps<{
  blocks: ForecastBlock[]
  ageDays: number | null
  stale: boolean
}>()

function fieldText(f: ForecastField): string {
  if (f.value === null || f.value === undefined) return '—'
  if (f.format === 'pct' && typeof f.value === 'number') return pct(f.value)
  if (f.format === 'money' && typeof f.value === 'number') return money(f.value)
  if (f.format === 'int' && typeof f.value === 'number') {
    return String(Math.round(f.value))
  }
  if (f.format === 'num' && typeof f.value === 'number') return num(f.value)
  return String(f.value)
}

/** 空块的原因文案——按块给具体原因，不说「暂无数据」。 */
const EMPTY_TEXT: Record<string, string> = {
  yjyg: '该标的最近一期无业绩预告（业绩平稳时不需要强制预告）',
  yjkb: '该标的未发布业绩快报（多数公司在预告与正式报告之间不发快报）',
  next_disclosure: '无预约披露安排（尚未预约或已过预约期）',
}
</script>

<template>
  <div>
    <p v-if="stale && ageDays !== null" class="wb-warn">
      最新预告的报告期距数据截至日 {{ ageDays }} 天。「最新」不等于
      「近期」——该标的可能已不在预告义务范围内，这条不代表当前预期。
    </p>

    <section v-for="b in blocks" :key="b.key">
      <h2 class="wb-h2">{{ b.title }}</h2>
      <StateBlock v-if="b.empty" kind="empty" :title="EMPTY_TEXT[b.key] ?? '无数据'"
                  hint="上游确实没有这一项，不是读取失败。" />
      <div v-else class="wb-kvs">
        <div v-for="f in b.fields" :key="f.key" class="wb-kv"
             :class="{ wide: f.format === 'text' && f.key === 'content' }">
          <span>{{ f.label }}</span>
          <b>{{ fieldText(f) }}</b>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
section + section {
  margin-top: var(--wb-sp-6);
}

.wb-kv.wide {
  grid-column: 1 / -1;
}

.wb-kv.wide b {
  font-weight: 400;
  color: var(--wb-text-secondary);
  line-height: 1.7;
}
</style>
