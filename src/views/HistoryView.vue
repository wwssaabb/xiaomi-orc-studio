<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import ResultPanel from '../components/ResultPanel.vue'
import { useHistory } from '../stores/history'
import { formatDuration, formatTime } from '../lib/format'
import { useToast } from '../lib/toast'
import type { HistoryItem } from '../lib/types'

const history = useHistory()
const toast = useToast()
const filter = ref<'all' | 'document' | 'kie' | 'vqa'>('all')
const selected = ref<HistoryItem | null>(null)

const filters: { id: typeof filter.value; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'document', label: '文档解析' },
  { id: 'kie', label: '信息抽取' },
  { id: 'vqa', label: '图文问答' },
]

const items = computed(() =>
  filter.value === 'all' ? history.state.items : history.state.items.filter((item) => item.kind === filter.value),
)

function kindLabel(kind: HistoryItem['kind']): string {
  if (kind === 'kie') return '信息抽取'
  if (kind === 'vqa') return '图文问答'
  return '文档解析'
}

function footLabel(item: HistoryItem): string {
  if (item.kind === 'kie') return 'JSON'
  if (item.kind === 'vqa') return '问答'
  if (item.source === 'pdf') return 'PDF'
  return item.mode === 'region' ? '区域' : '整页'
}

function remove(item: HistoryItem): void {
  history.remove(item.id)
  if (selected.value?.id === item.id) selected.value = null
  toast.success('已删除')
}

function clearAll(): void {
  history.clear()
  selected.value = null
  toast.success('历史已清空')
}
</script>

<template>
  <div class="page">
    <section class="hero" style="padding-bottom: 16px">
      <div>
        <h1>历史记录</h1>
        <p>结果仅保存在本机浏览器（localStorage），最多保留最近 30 条，不会上传到任何服务器。</p>
      </div>
      <div class="hero-badges">
        <button v-if="history.count.value" class="btn btn-ghost" style="min-height: 38px" @click="clearAll">
          <AppIcon name="trash" :size="15" />清空历史
        </button>
      </div>
    </section>

    <div class="card" style="margin-bottom: 16px">
      <div class="card-body" style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 12px 16px">
        <button
          v-for="item in filters"
          :key="item.id"
          class="chip"
          :class="{ active: filter === item.id }"
          @click="filter = item.id"
        >
          {{ item.label }}
        </button>
        <span style="margin-left: auto; font-size: 12px; color: var(--muted)">{{ items.length }} 条记录</span>
      </div>
    </div>

    <div v-if="!items.length" class="card">
      <div class="empty-state" style="min-height: 320px">
        <div class="big-icon"><AppIcon name="history" :size="30" /></div>
        <h3>还没有解析记录</h3>
        <p>回到工作台上传一张图片，识别完成后结果会自动出现在这里。</p>
        <RouterLink to="/" class="btn btn-primary" style="margin-top: 6px">去解析</RouterLink>
      </div>
    </div>

    <div v-else class="history-grid">
      <article v-for="item in items" :key="item.id" class="history-card">
        <div class="history-thumb">
          <img v-if="item.thumb" :src="item.thumb" :alt="item.title" />
          <AppIcon v-else name="file" :size="30" />
        </div>
        <div class="history-content">
          <div class="history-title">
            <span>{{ item.title }}</span>
            <span class="pill pill-brand">{{ kindLabel(item.kind) }}</span>
          </div>
          <p class="history-excerpt">{{ item.text || '（无预览内容）' }}</p>
          <div style="display: flex; gap: 6px; align-items: center; font-size: 11px; color: var(--muted)">
            <AppIcon name="clock" :size="12" />
            {{ formatTime(item.createdAt) }} · {{ formatDuration(item.elapsedMs) }}
          </div>
        </div>
        <div class="history-foot">
          <span class="pill">{{ footLabel(item) }}</span>
          <span class="spacer" />
          <div class="history-actions">
            <button class="icon-mini" title="查看结果" @click="selected = item"><AppIcon name="external" :size="15" /></button>
            <button class="icon-mini danger" title="删除" @click="remove(item)"><AppIcon name="trash" :size="15" /></button>
          </div>
        </div>
      </article>
    </div>

    <section v-if="selected" style="margin-top: 18px">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px">
        <h2 style="margin: 0; font-size: 16px">结果详情</h2>
        <span class="pill">{{ selected.title }}</span>
        <button class="mini-btn" style="margin-left: auto" @click="selected = null">
          <AppIcon name="close" :size="14" />关闭
        </button>
      </div>
      <ResultPanel :result="selected.result" :elapsed-ms="selected.elapsedMs" @restart="selected = null" />
    </section>
  </div>
</template>
