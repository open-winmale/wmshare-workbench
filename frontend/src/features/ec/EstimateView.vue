<script setup lang="ts">
/**
 * EC 试算（`/api/ec/estimate`）：**零请求**。
 *
 * 这一页的意义是把「花钱之前先算账」做成一个可独立使用的入口：
 * 跑任何工具之前，先问一句「这要花多少」。
 */
import { computed, onMounted, ref } from 'vue'

import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import PanelShell from '../../components/ui/PanelShell.vue'
import StateBlock from '../../components/ui/StateBlock.vue'
import { ACTION_LABEL, useTool } from '../../composables/useTool'

interface Estimate {
  pred_lo: number | null
  pred_hi: number | null
  actual: number | null
  model: string
}

interface EcData {
  target: string
  params: Record<string, unknown>
  estimate: Estimate
  max_ec: number
  over_budget: boolean
  estimable: string[]
  message: string
}

const { data, loading, error, load } = useTool<EcData>('ec_estimate')
const target = ref('screener.query')
const paramsText = ref('{}')
const parseError = ref('')

const range = computed(() => {
  const e = data.value?.estimate
  if (!e || e.pred_lo === null || e.pred_hi === null) return '未知'
  return `${e.pred_lo.toLocaleString()} – ${e.pred_hi.toLocaleString()} EC`
})

function run(): void {
  parseError.value = ''
  let parsed: unknown = {}
  try {
    parsed = paramsText.value.trim() ? JSON.parse(paramsText.value) : {}
  } catch (exc) {
    parseError.value = `参数 JSON 非法：${exc instanceof Error ? exc.message : exc}`
    return
  }
  load({ target: target.value, params: parsed })
}

onMounted(run)
</script>

<template>
  <PanelShell title="EC 试算" subtitle="试算不发起任何上游请求"
              :loading="loading" @refresh="run()">
    <div class="wb-bar">
      <label>
        接口
        <select v-model="target" class="wb-input" @change="run()">
          <option v-for="t in data?.estimable ?? ['screener.query']" :key="t"
                  :value="t">{{ t }}</option>
        </select>
      </label>
      <input v-model="paramsText" class="wb-input grow" type="text"
             placeholder='参数 JSON，如 {"limit": 50}' @keyup.enter="run()" />
      <button class="wb-btn" type="button" @click="run()">试算</button>
    </div>

    <LoadingSkeleton v-if="loading" :rows="3" />

    <StateBlock v-else-if="error" kind="error" title="试算失败"
                :detail="error.message"
                :action-label="ACTION_LABEL[error.action] ?? '重试'"
                @action="run()" />

    <template v-else>
      <div class="hero">
        <span class="label">预估消耗</span>
        <span class="value" :class="{ over: data?.over_budget }">{{ range }}</span>
        <span class="model">模型：{{ data?.estimate.model ?? 'none' }}</span>
      </div>

      <p class="msg" :class="{ over: data?.over_budget }">{{ data?.message }}</p>

      <div class="wb-kvs">
        <div class="wb-kv"><span>单次上限</span><b>{{ (data?.max_ec ?? 0).toLocaleString() }} EC</b></div>
        <div class="wb-kv"><span>超预算</span><b :class="data?.over_budget ? 'over' : ''">{{ data?.over_budget ? '是（需二次确认）' : '否' }}</b></div>
        <div class="wb-kv"><span>实际消耗</span><b>{{ data?.estimate.actual ?? '尚未产生' }}</b></div>
      </div>

      <p v-if="parseError" class="err">{{ parseError }}</p>

      <div class="note">
        <h2>为什么「未知」不是 0</h2>
        <p>
          没有成本模型时这里显示「未知」。如果显示 0，用户会读成「免费」，
          然后在最贵的操作上毫无防备——那是本工具最不能犯的错。
        </p>
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
  flex: 1 1 260px;
  min-width: 160px;
}

.btn:hover {
  background: var(--wb-bg-hover);
  color: var(--wb-text-primary);
}

.hero {
  display: flex;
  align-items: baseline;
  gap: var(--wb-sp-5);
  padding: var(--wb-sp-7) var(--wb-sp-6) var(--wb-sp-4);
  flex-wrap: wrap;
}

.label {
  font-size: var(--wb-fs-2);
  color: var(--wb-text-tertiary);
}

.value {
  font-size: var(--wb-fs-7);
  font-variant-numeric: tabular-nums;
  color: var(--wb-text-primary);
}

.value.over {
  color: var(--wb-warning);
}

.model {
  font-size: var(--wb-fs-1);
  color: var(--wb-text-dim);
}

.msg {
  margin: 0;
  padding: 0 var(--wb-sp-6) var(--wb-sp-5);
  color: var(--wb-text-tertiary);
  font-size: var(--wb-fs-2);
  max-width: 60em;
}

.msg.over {
  color: var(--wb-warning);
}

.kv span {
  color: var(--wb-text-tertiary);
}

.kv b {
  font-weight: 500;
}

.over {
  color: var(--wb-warning);
}

.err {
  margin: 0;
  padding: 0 var(--wb-sp-6);
  color: var(--wb-up);
  font-size: var(--wb-fs-2);
}

.note {
  margin: 0 var(--wb-sp-6) var(--wb-sp-6);
  padding: var(--wb-sp-4);
  background: var(--wb-bg-raised);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-2);
}

.note h2 {
  margin: 0 0 var(--wb-sp-2);
  font-size: var(--wb-fs-3);
  font-weight: 500;
  color: var(--wb-text-secondary);
}

.note p {
  margin: 0;
  font-size: var(--wb-fs-2);
  color: var(--wb-text-tertiary);
  max-width: 60em;
}
</style>
