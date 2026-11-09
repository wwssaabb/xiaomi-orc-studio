import { computed, reactive, watch } from 'vue'
import type { HistoryItem, RunResult } from '../lib/types'
import { truncate } from '../lib/format'

const STORAGE_KEY = 'xiaomi-ocr-studio.history.v1'
const LIMIT = 30

function load(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as HistoryItem[]
    return Array.isArray(parsed) ? parsed.slice(0, LIMIT) : []
  } catch {
    return []
  }
}

const state = reactive<{ items: HistoryItem[] }>({ items: load() })

watch(
  () => state.items,
  (items) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, LIMIT)))
    } catch {
      /* quota exceeded: drop thumbnails, keep text */
      try {
        const slim = items.slice(0, LIMIT).map(({ thumb: _thumb, ...rest }) => rest)
        localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
      } catch {
        /* give up silently */
      }
    }
  },
  { deep: true },
)

export function useHistory() {
  function add(item: Omit<HistoryItem, 'id' | 'createdAt'>): HistoryItem {
    const entry: HistoryItem = {
      ...item,
      id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      createdAt: Date.now(),
    }
    state.items.unshift(entry)
    state.items = state.items.slice(0, LIMIT)
    return entry
  }

  function remove(id: string): void {
    state.items = state.items.filter((item) => item.id !== id)
  }

  function clear(): void {
    state.items = []
  }

  function titleFor(kind: HistoryItem['kind'], result: RunResult): string {
    if (kind === 'kie') return '关键信息抽取'
    if (kind === 'vqa') return '图文问答'
    return result.kind === 'document' && result.pages ? `文档解析 · ${result.pages} 页` : '文档解析'
  }

  function excerptFor(result: RunResult): string {
    if (result.kind === 'vqa') return result.answer
    if (result.kind === 'kie') return JSON.stringify(result.json ?? {}, null, 0)
    return truncate(result.markdown.replace(/<[^>]+>/g, ' ').replace(/[#*`>]/g, ''), 160)
  }

  return { state, add, remove, clear, titleFor, excerptFor, count: computed(() => state.items.length) }
}
