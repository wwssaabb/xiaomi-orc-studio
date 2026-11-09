import { reactive } from 'vue'

export interface ToastItem {
  id: number
  message: string
  type: 'info' | 'success' | 'error'
}

const state = reactive<{ items: ToastItem[] }>({ items: [] })
let seq = 0

export function useToast() {
  function push(message: string, type: ToastItem['type'] = 'info', duration = 2600): void {
    const id = ++seq
    state.items.push({ id, message, type })
    window.setTimeout(() => {
      const index = state.items.findIndex((item) => item.id === id)
      if (index >= 0) state.items.splice(index, 1)
    }, duration)
  }

  return {
    state,
    toast: push,
    info: (message: string) => push(message, 'info'),
    success: (message: string) => push(message, 'success'),
    error: (message: string) => push(message, 'error', 3600),
  }
}
