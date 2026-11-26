<script setup lang="ts">
/**
 * 页顶状态条（从 `App.vue` 拆出）。
 *
 * **它承载「不骗人」原则的第一道闸**：任何时候都要能看出
 * 「当前是真实数据还是未接入」，未接入时说明原因。
 */
export interface AppInfo {
  version: string
  /** `credentials` / `public_pool` / `missing` */
  auth_mode: string
  /** 页顶标签（后端给中文文案，前端不自己拼） */
  mode_label: string
  /** 是否真实数据（含免注册） */
  real: boolean
  /** 未接入的原因（已接入为空串） */
  reason: string
  credentials: { configured: boolean; source: string }
  wmshare_available: boolean
}

defineProps<{
  info: AppInfo | null
  infoError: string
  theme: 'obsidian' | 'daylight'
  cvd: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
  toggleCvd: []
  toggleNav: []
}>()
</script>

<template>
  <header class="topbar">
    <button class="menu" type="button" title="展开导航" @click="emit('toggleNav')">
      ☰
    </button>
    <div class="brand">
      <span class="mark" aria-hidden="true">
        <svg viewBox="0 0 20 20" width="20" height="20">
          <rect class="mark-bg" x="0" y="0" width="20" height="20" rx="5" />
          <path class="mark-fg" d="M5 13V9M10 13V6M15 13V8" />
        </svg>
      </span>
      <span class="name">wmshare-workbench</span>
    </div>

    <div class="spacer" />

    <span v-if="infoError" class="badge error" :title="infoError">后端未连接</span>
    <template v-else-if="info">
      <!--
        三态而不是两态：`免注册` 也是真实数据，不标警示；`未接入` 用琥珀标
        并给出原因与补救指引（悬浮可见），绝不冒充有数据。
      -->
      <span class="badge" :class="info.auth_mode"
            :title="info.real ? '' : info.reason">
        {{ info.mode_label }}
      </span>
      <span v-if="!info.wmshare_available" class="badge warn">未安装 wmshare</span>
      <span class="badge muted">v{{ info.version }}</span>
    </template>

    <button class="wb-btn" type="button" title="切换色觉障碍友好配色"
            @click="emit('toggleCvd')">
      {{ cvd ? 'CVD 开' : 'CVD' }}
    </button>
    <button class="wb-btn" type="button" title="切换主题" @click="emit('toggleTheme')">
      {{ theme === 'obsidian' ? '暗色' : '亮色' }}
    </button>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-4);
  height: var(--wb-topbar-h);
  padding: 0 var(--wb-sp-8);
  border-bottom: 1px solid var(--wb-border-dim);
  background: var(--wb-bg-surface);
  flex: 0 0 auto;
  z-index: var(--wb-z-sticky);
}

.menu {
  display: none;
  background: transparent;
  border: 1px solid var(--wb-border-med);
  border-radius: var(--wb-r-2);
  color: var(--wb-text-secondary);
  cursor: pointer;
  padding: var(--wb-sp-1) var(--wb-sp-3);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--wb-sp-3);
  font-size: var(--wb-fs-5);
}

.mark {
  display: inline-flex;
  width: 20px;
  height: 20px;
}

.mark-bg {
  fill: var(--wb-accent);
}

.mark-fg {
  fill: none;
  stroke: var(--wb-bg-surface);
  stroke-width: 2;
  stroke-linecap: round;
}

.name {
  font-weight: 600;
  letter-spacing: 0.01em;
}

.spacer {
  flex: 1;
}

.badge {
  font-size: var(--wb-fs-2);
  padding: var(--wb-sp-1) var(--wb-sp-4);
  border: 1px solid var(--wb-border-dim);
  border-radius: var(--wb-r-2);
  color: var(--wb-text-secondary);
  background: var(--wb-bg-raised);
  white-space: nowrap;
}

.badge.missing {
  border-color: var(--wb-warning);
  color: var(--wb-warning);
  background: transparent;
}

/* 免注册也是真实数据 —— 用信息蓝；自有凭证保持中性，不占用涨跌色 */
.badge.public_pool {
  border-color: var(--wb-info);
  color: var(--wb-info);
  background: var(--wb-accent-bg);
}

.badge.credentials {
  border-color: var(--wb-border-med);
  color: var(--wb-text-secondary);
  background: var(--wb-bg-raised);
}

.badge.warn {
  border-color: var(--wb-warning);
  color: var(--wb-warning);
}

.badge.error {
  border-color: var(--wb-up);
  color: var(--wb-up);
}

.badge.muted {
  color: var(--wb-text-tertiary);
}

@media (max-width: 820px) {
  .menu {
    display: block;
  }

  .name {
    display: none;
  }
}
</style>
