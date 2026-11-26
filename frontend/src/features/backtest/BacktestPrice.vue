<script setup lang="ts">
/**
 * 回测的价格走势卡：K 线 + 买卖点标记。
 *
 * **买卖点要标在价格上，不是净值上**——净值受现金与费用影响，标在它
 * 上面会把「现金流折线」当成价格走势。从回测页拆出来是因为这一块有
 * 自己的口径说明（另一次区间取数、位置与成交明细对账），不是回测页
 * 的主计算路径。
 *
 * 区间 hint 写**数据实际首末日**（bars 是升序的，首末即事实），不是
 * 请求参数 begin/end——上游可能没有数据到请求终点。
 */
import { computed } from 'vue'

import KLineChart, { type Bar, type Mark } from '../../components/ui/KLineChart.vue'
import AsOfChip from '../../components/ui/AsOfChip.vue'

const props = defineProps<{
  /** 已升序的区间日 K（后端 `normalize_bars` 保证） */
  bars: Bar[]
  marks: Mark[]
  begin: string
  end: string
  /** 页顶「截至」（净值数据的末日）；价格末日与之不同时显示块级 chip */
  pageAsOf?: string
}>()

const firstDate = computed(() => props.bars[0]?.date ?? '')
const lastDate = computed(() => props.bars[props.bars.length - 1]?.date ?? '')
const differsFromPage = computed(() =>
  !!lastDate.value && !!props.pageAsOf && lastDate.value !== props.pageAsOf)
</script>

<template>
  <div class="wb-card">
    <h2 class="wb-h2">
      价格走势（含买卖点）
      <AsOfChip v-if="differsFromPage" :date="lastDate" />
    </h2>
    <KLineChart :bars="bars" :marks="marks" :height="380" />
    <p class="wb-hint">
      价格为 {{ firstDate }} → {{ lastDate }} 的日 K（另一次区间取数，
      请求区间 {{ begin }} → {{ end }}）；
      买卖点位置与成交明细的日期价格一致。
    </p>
  </div>
</template>
