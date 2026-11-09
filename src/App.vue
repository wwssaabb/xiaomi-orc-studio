<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import { useHealth } from './lib/health'
import { useToast } from './lib/toast'
import { useHistory } from './stores/history'

const route = useRoute()
const { state: healthState, refresh, statusLabel, statusClass, startPolling } = useHealth()
const history = useHistory()
const toasts = useToast().state

const theme = ref<'light' | 'dark'>(loadTheme())

function loadTheme(): 'light' | 'dark' {
  const saved = localStorage.getItem('xiaomi-ocr-studio.theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

watch(
  theme,
  (value) => {
    document.documentElement.dataset.theme = value
    localStorage.setItem('xiaomi-ocr-studio.theme', value)
  },
  { immediate: true },
)

const pageTitle = computed(() => {
  if (route.name === 'history') return '历史记录'
  if (route.name === 'guide') return '使用指南'
  return '解析工作台'
})

onMounted(() => {
  void refresh()
  startPolling()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark"><AppIcon name="scan" :size="21" /></span>
        <div>
          <div class="brand-title">Xiaomi-OCR Studio</div>
          <div class="brand-sub">本地文档智能解析</div>
        </div>
      </div>

      <nav class="nav">
        <div class="nav-label">工作区</div>
        <RouterLink class="nav-link" to="/"><AppIcon name="scan" />解析工作台</RouterLink>
        <RouterLink class="nav-link" :to="{ name: 'history' }">
          <AppIcon name="history" />历史记录
          <span v-if="history.count.value" class="pill" style="margin-left: auto">{{ history.count.value }}</span>
        </RouterLink>
        <RouterLink class="nav-link" :to="{ name: 'guide' }"><AppIcon name="book" />使用指南</RouterLink>
      </nav>

      <div class="sidebar-foot">
        <div class="service-card">
          <strong>本地推理引擎</strong>
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px">
            <span :class="statusClass"><span class="dot" />{{ statusLabel }}</span>
          </div>
          <div v-if="healthState.health" class="model-line" :title="`${healthState.health.backend} · ${healthState.health.model}`">
            {{ healthState.health.backend }} · {{ healthState.health.model }}
          </div>
          <div v-else>{{ healthState.loading ? '正在检测服务…' : '服务未响应' }}</div>
        </div>
        <button class="btn btn-ghost btn-block" style="min-height: 38px" @click="refresh">
          <span v-if="healthState.loading" class="spinner" style="width: 13px; height: 13px" />
          <AppIcon v-else name="refresh" :size="15" />
          刷新连接状态
        </button>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <span class="mobile-brand brand-mark" style="width: 32px; height: 32px; border-radius: 10px">
          <AppIcon name="scan" :size="18" />
        </span>
        <span class="topbar-title">{{ pageTitle }}</span>
        <div class="topbar-meta">
          <span :class="statusClass"><span class="dot" :class="{ 'dot-pulse': healthState.health?.modelOnline }" />{{ statusLabel }}</span>
          <span class="pill">Xiaomi-OCR-0 · 0.8B</span>
        </div>
        <div class="topbar-actions">
          <button class="icon-btn" :title="theme === 'dark' ? '切换浅色' : '切换深色'" @click="theme = theme === 'dark' ? 'light' : 'dark'">
            <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="17" />
          </button>
        </div>
      </header>

      <RouterView />

      <nav class="mobile-tabbar">
        <RouterLink to="/"><AppIcon name="scan" :size="20" />工作台</RouterLink>
        <RouterLink :to="{ name: 'history' }"><AppIcon name="history" :size="20" />历史</RouterLink>
        <RouterLink :to="{ name: 'guide' }"><AppIcon name="book" :size="20" />指南</RouterLink>
      </nav>
    </main>

    <div class="toast-stack">
      <div v-for="item in toasts.items" :key="item.id" class="toast" :class="item.type">
        <AppIcon :name="item.type === 'error' ? 'alert' : item.type === 'success' ? 'check' : 'info'" :size="16" />
        {{ item.message }}
      </div>
    </div>
  </div>
</template>
