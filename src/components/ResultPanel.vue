<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { renderMarkdown } from '../lib/markdown'
import type { RunResult } from '../lib/types'

const props = defineProps<{
  result: RunResult
  elapsedMs?: number
}>()

const emit = defineEmits<{
  (event: 'restart'): void
}>()

const tab = ref<'render' | 'source' | 'structured'>('render')

const isDocument = computed(() => props.result.kind === 'document')
const isKie = computed(() => props.result.kind === 'kie')

const documentResult = computed(() => (props.result.kind === 'document' ? props.result : null))
const kieResult = computed(() => (props.result.kind === 'kie' ? props.result : null))
const vqaResult = computed(() => (props.result.kind === 'vqa' ? props.result : null))

const rendered = computed(() => (documentResult.value ? renderMarkdown(documentResult.value.markdown) : ''))

const structuredRows = computed(() => {
  const data = kieResult.value?.json
  if (!data) return []
  return Object.entries(data).map(([key, value]) => ({ key, value: formatValue(value) }))
})

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value || '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

import { copyText, downloadBlob } from '../lib/files'
import { useToast } from '../lib/toast'
import { formatDuration } from '../lib/format'

const toast = useToast()

async function copy(): Promise<void> {
  const text =
    documentResult.value?.markdown ??
    (kieResult.value?.json ? JSON.stringify(kieResult.value.json, null, 2) : '') ??
    vqaResult.value?.answer ??
    ''
  if (!text) return
  try {
    await copyText(text)
    toast.success('已复制到剪贴板')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '复制失败')
  }
}

async function download(): Promise<void> {
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  if (documentResult.value) {
    await downloadBlob(`ocr-${stamp}.md`, documentResult.value.markdown)
    toast.success('Markdown 已下载')
    return
  }
  if (kieResult.value?.json) {
    await downloadBlob(`kie-${stamp}.json`, JSON.stringify(kieResult.value.json, null, 2), 'application/json')
    toast.success('JSON 已下载')
    return
  }
  if (vqaResult.value) {
    await downloadBlob(`vqa-${stamp}.txt`, vqaResult.value.answer, 'text/plain;charset=utf-8')
    toast.success('答案已下载')
  }
}

const regionLabel = computed(() => {
  const mode = documentResult.value?.mode
  if (mode === 'region') return '区域解析'
  if (mode === 'page_fallback') return '整页解析（区域回退）'
  return '整页解析'
})
</script>

<template>
  <div class="card result-card">
    <div class="card-head">
      <div class="card-title">识别结果</div>
      <span v-if="isDocument" class="pill pill-brand">{{ regionLabel }}</span>
      <span v-else-if="isKie" class="pill pill-brand">信息抽取</span>
      <span v-else class="pill pill-brand">图文问答</span>
      <div style="margin-left: auto; display: flex; gap: 6px">
        <button class="icon-mini" title="复制结果" @click="copy"><AppIcon name="copy" :size="15" /></button>
        <button class="icon-mini" title="下载结果" @click="download"><AppIcon name="download" :size="15" /></button>
        <button class="icon-mini" title="重新选择" @click="emit('restart')"><AppIcon name="refresh" :size="15" /></button>
      </div>
    </div>

    <div class="result-body">
      <div v-if="isDocument" class="result-toolbar">
        <div class="tabs">
          <button :class="{ active: tab === 'render' }" @click="tab = 'render'">渲染</button>
          <button :class="{ active: tab === 'source' }" @click="tab = 'source'">Markdown</button>
        </div>
        <div class="toolbar-spacer" />
        <button class="mini-btn primary" @click="copy"><AppIcon name="copy" :size="14" />复制</button>
        <button class="mini-btn" @click="download"><AppIcon name="download" :size="14" />下载 .md</button>
      </div>

      <div v-else-if="isKie" class="result-toolbar">
        <div class="tabs">
          <button :class="{ active: tab !== 'structured' }" @click="tab = 'render'">字段视图</button>
          <button :class="{ active: tab === 'structured' }" @click="tab = 'structured'">JSON</button>
        </div>
        <div class="toolbar-spacer" />
        <button class="mini-btn primary" @click="copy"><AppIcon name="copy" :size="14" />复制 JSON</button>
      </div>

      <div class="result-scroll">
        <template v-if="isDocument">
          <div v-if="documentResult?.reason" class="warn-banner" style="margin-bottom: 14px">
            <AppIcon name="info" :size="15" />{{ documentResult.reason }}
          </div>
          <div v-if="tab === 'render'" class="markdown" v-html="rendered" />
          <pre v-else class="code-view">{{ documentResult?.markdown }}</pre>
        </template>

        <template v-else-if="isKie">
          <div v-if="kieResult?.warning" class="warn-banner" style="margin-bottom: 14px">
            <AppIcon name="alert" :size="15" />{{ kieResult.warning }}
          </div>
          <div v-if="tab === 'render'">
            <div v-if="structuredRows.length" class="json-view">
              <div v-for="row in structuredRows" :key="row.key" class="json-row">
                <div class="json-key">{{ row.key }}</div>
                <div class="json-value">{{ row.value }}</div>
              </div>
            </div>
            <div v-else class="empty-state" style="padding: 30px 10px">
              <AppIcon name="extract" :size="28" />
              <p>没有解析出字段，可尝试补充字段名后重试。</p>
            </div>
            <pre v-if="kieResult?.raw" class="code-view" style="margin-top: 14px">{{ kieResult.raw }}</pre>
          </div>
          <pre v-else class="code-view">{{ JSON.stringify(kieResult?.json ?? {}, null, 2) }}</pre>
        </template>

        <template v-else>
          <div class="answer">{{ vqaResult?.answer }}</div>
          <p style="margin: 14px 0 0; font-size: 12px; color: var(--muted)">
            问题：{{ vqaResult?.question }}
          </p>
        </template>
      </div>
    </div>

    <div class="result-meta">
      <AppIcon name="clock" :size="13" />
      <span>耗时 {{ formatDuration(elapsedMs ?? props.result.elapsedMs) }}</span>
      <span v-if="documentResult?.pages">· {{ documentResult.pages }} 页</span>
      <span v-if="documentResult?.regions">· {{ documentResult.regions }} 个版面区域</span>
      <span v-if="isDocument">· {{ documentResult?.markdown.length ?? 0 }} 字符</span>
      <div style="flex: 1" />
      <span>本地推理 · 数据不出设备</span>
    </div>
  </div>
</template>
