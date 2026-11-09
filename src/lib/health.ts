import { computed, reactive } from 'vue'
import { getHealth } from './api'
import type { Health } from './types'

const state = reactive<{
  health: Health | null
  loading: boolean
  error: string
  lastChecked: number
}>({
  health: null,
  loading: false,
  error: '',
  lastChecked: 0,
})

let inflight: Promise<void> | null = null
let timer: number | null = null

async function refresh(): Promise<void> {
  if (inflight) return inflight
  state.loading = true
  state.error = ''
  inflight = (async () => {
    try {
      state.health = await getHealth()
      state.lastChecked = Date.now()
    } catch (error) {
      state.error = error instanceof Error ? error.message : '服务状态获取失败'
    } finally {
      state.loading = false
      inflight = null
    }
  })()
  return inflight
}

function startPolling(interval = 30_000): void {
  if (timer !== null) return
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void refresh()
  }, interval)
}

const online = computed(() => Boolean(state.health?.modelOnline && state.health?.engineReady))

const statusLabel = computed(() => {
  if (!state.health) return '检测中'
  if (!state.health.engineReady) return '引擎不可用'
  if (!state.health.modelOnline) return '模型未连接'
  return '本地就绪'
})

const statusClass = computed(() => {
  if (!state.health) return 'pill'
  if (!online.value) return 'pill pill-danger'
  return 'pill pill-success'
})

export function useHealth() {
  return { state, refresh, startPolling, online, statusLabel, statusClass }
}
