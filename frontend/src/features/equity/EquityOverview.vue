<script setup lang="ts">
/**
 * 个股概览卡片（从 `EquityView` 拆出）。
 *
 * 概览是唯一默认加载的分区，字段最多（价量/均线/市值/股息）。单独成组件
 * 后，其余分区（估值序列/财报/分红）可以各自保持很短。
 */
import { computed } from 'vue'

import { money, num, pct, price, trendClass } from '../../composables/format'

export interface Snapshot {
  name?: string
  industry?: string
  close?: number
  percent?: number
  chg_20d?: number
  roi_1y?: number
  ma20?: number
  ma60?: number
  mv?: number
  vol_ratio_5?: number
  kline_date?: string
  /** 现价来自盘中快照（live 日期严格新于收盘快照日才置位） */
  live?: boolean
  is_st?: boolean
  is_suspend?: boolean
}

/** 概览只需要两个值；分红分区的完整结构在同名模块里另行定义。 */
export interface DividendBrief {
  yield_ttm?: number
  dps_ttm?: number
  quote_date?: string
}

const props = defineProps<{
  symbol: string
  snapshot: Snapshot
  dividend: DividendBrief
}>()

interface Tile {
  label: string
  value: string
  trend?: number | null
}

const tiles = computed<Tile[]>(() => {
  const s = props.snapshot
  const d = props.dividend
  return [
    { label: '总市值', value: money(s.mv) },
    { label: 'MA20', value: price(s.ma20) },
    { label: 'MA60', value: price(s.ma60) },
    { label: '5 日量比', value: num(s.vol_ratio_5) },
    { label: '20 日', value: pct(s.chg_20d), trend: s.chg_20d },
    { label: '近 1 年', value: pct(s.roi_1y), trend: s.roi_1y },
    { label: 'TTM 股息率', value: pct(d.yield_ttm) },
    { label: '每股分红 TTM', value: num(d.dps_ttm) },
  ]
})
</script>

<template>
  <div class="head">
    <div>
      <h2>{{ snapshot.name ?? symbol }}</h2>
      <p class="meta">
        {{ snapshot.industry ?? '—' }} · {{ snapshot.kline_date ?? '—' }}
        <span v-if="snapshot.is_st" class="st">ST</span>
        <span v-if="snapshot.is_suspend" class="st">停牌</span>
      </p>
    </div>
    <div class="price">
      <span class="big" :class="trendClass(snapshot.percent)">
        {{ price(snapshot.close) }}
      </span>
      <span :class="trendClass(snapshot.percent)">{{ pct(snapshot.percent) }}</span>
      <span v-if="snapshot.live" class="lv" title="现价来自盘中快照（休市=最近收盘）">实时</span>
    </div>
  </div>

  <div class="wb-kvs tiles">
    <div v-for="t in tiles" :key="t.label" class="wb-kv">
      <span>{{ t.label }}</span>
      <b :class="t.trend === undefined ? '' : trendClass(t.trend)">{{ t.value }}</b>
    </div>
  </div>

  <!-- 两个块的截止日来自两次独立上游，各显各的（不同时页顶只取了行情那个） -->
  <p v-if="dividend.quote_date" class="divmeta">
    <span class="wb-chip">分红快照 {{ dividend.quote_date }}</span>
    <span v-if="dividend.quote_date !== snapshot.kline_date" class="why">
      与行情快照日期不同：分红数据另有上游
    </span>
  </p>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  gap: var(--wb-sp-6);
  flex-wrap: wrap;
}

h2 {
  margin: 0;
  font-size: var(--wb-fs-5);
  font-weight: 500;
}

.meta {
  margin: var(--wb-sp-2) 0 0;
  font-size: var(--wb-fs-2);
  color: var(--wb-text-tertiary);
}

.st {
  margin-left: var(--wb-sp-2);
  color: var(--wb-warning);
}

.price {
  margin-left: auto;
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-4);
}

/* 「实时」小标：现价来自盘中快照（样式同自选页 .lv） */
.lv {
  font-size: var(--wb-fs-1);
  color: var(--wb-accent);
}

.big {
  font-size: var(--wb-fs-7);
  font-variant-numeric: tabular-nums;
}

.tiles {
  margin-top: var(--wb-sp-6);
}

.divmeta {
  margin: var(--wb-sp-4) 0 0;
  display: flex;
  align-items: center;
  gap: var(--wb-sp-3);
}

.why {
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
}
</style>
