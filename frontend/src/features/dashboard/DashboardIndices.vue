<script setup lang="ts">
/**
 * 今日盘面 · 三大指数卡（winmale 式）：现价 + 涨跌 + 分时 mini + 高/低。
 *
 * 数据契约（后端 `tools/dashboard/pulse.py`）：cards 只含通过 date 守卫的
 * 指数（上游对断供键返回兜底假行、date 停在上一交易日，后端已滤）；
 * `minute` 为升序 `{t, close}`，创业板指上游无分时 → 无该键 → 卡上无小图，
 * **不是**「缺数据坏了」——那是上游缺口，如实。
 */
import LineChart from '../../components/ui/LineChart.vue'
import { pct, price, trendClass } from '../../composables/format'

export interface IndexCard {
  key: string
  label: string
  close?: number | null
  percent?: number | null
  change?: number | null
  high?: number | null
  low?: number | null
  date?: string
  minute?: { t?: string; close?: number | null }[]
}

defineProps<{ cards: IndexCard[] }>()
</script>

<template>
  <div class="cards">
    <div v-for="c in cards" :key="c.key" class="wb-card card">
      <div class="head">
        <span class="name">{{ c.label }}</span>
        <span class="chip">盘中</span>
      </div>
      <div class="quote" :class="trendClass(c.percent)">
        <span class="close">{{ price(c.close) }}</span>
        <span class="chg">
          {{ (c.change ?? 0) > 0 ? '+' : '' }}{{ price(c.change) }}
          {{ pct(c.percent) }}
        </span>
      </div>
      <LineChart v-if="(c.minute?.length ?? 0) > 1" class="spark"
                 :series="[{ name: c.label,
                             data: c.minute!.map((p) => p.close ?? null) }]"
                 :x-labels="c.minute!.map((p) => p.t ?? '')"
                 area scale bare :height="64" />
      <p v-else class="nomin">该指数上游无分时（缺口如实，不画别家的）。</p>
      <div class="range">
        <span>高 {{ price(c.high) }}</span>
        <span>低 {{ price(c.low) }}</span>
      </div>
      <p class="date">{{ c.date }}（休市=最近收盘）</p>
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--wb-sp-4);
  padding: var(--wb-sp-6) var(--wb-sp-6) 0;
}

.card {
  padding: var(--wb-sp-4) var(--wb-sp-5);
  margin: 0;
}

.head {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-2);
}

.name {
  font-weight: 500;
}

.chip {
  font-size: var(--wb-fs-1);
  color: var(--wb-text-tertiary);
  border: 1px solid var(--wb-border-dim);
  border-radius: 999px;
  padding: 0 var(--wb-sp-2);
}

.quote {
  margin: var(--wb-sp-2) 0;
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-3);
}

.close {
  font-size: var(--wb-fs-6);
  font-variant-numeric: tabular-nums;
}

.spark {
  margin: var(--wb-sp-2) 0;
}

.nomin {
  margin: var(--wb-sp-3) 0;
  height: 64px;
  display: flex;
  align-items: center;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.range {
  display: flex;
  justify-content: space-between;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}

.date {
  margin: var(--wb-sp-2) 0 0;
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-1);
}
</style>
