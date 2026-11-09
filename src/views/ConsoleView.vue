<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import ResultPanel from '../components/ResultPanel.vue'
import { getSamples, runKie, runOcr, runPdf, runVqa } from '../lib/api'
import { assertSize, isPdf, prepareImage, readAsDataUrl } from '../lib/files'
import { useHealth } from '../lib/health'
import { useToast } from '../lib/toast'
import { useHistory } from '../stores/history'
import type { DocMode, RunResult, SampleItem, TaskKind } from '../lib/types'

interface Source {
  kind: 'image' | 'pdf'
  name: string
  size: number
  dataUrl: string
  thumb: string
}

const { state: healthState } = useHealth()
const history = useHistory()
const toast = useToast()

const tasks: { id: TaskKind; label: string; icon: string; desc: string }[] = [
  { id: 'document', label: '文档解析', icon: 'file', desc: '整页转 Markdown，自动还原表格与公式' },
  { id: 'kie', label: '信息抽取', icon: 'extract', desc: '按字段输出结构化 JSON' },
  { id: 'vqa', label: '图文问答', icon: 'message', desc: '针对图像内容提问并作答' },
]

const task = ref<TaskKind>('document')
const mode = ref<DocMode>('page')
const maxTokens = ref(2048)
const maxPages = ref(3)
const dpi = ref(150)
const fieldsText = ref('')
const question = ref('')

const source = ref<Source | null>(null)
const running = ref(false)
const error = ref('')
const result = ref<RunResult | null>(null)
const elapsed = ref(0)
const dragging = ref(false)
const samples = ref<SampleItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const cameraInput = ref<HTMLInputElement | null>(null)

let startedAt = 0
let ticker: number | null = null

const regionReady = computed(() => healthState.health?.capabilities.region ?? false)
const pdfReady = computed(() => healthState.health?.capabilities.pdf ?? false)

const canRun = computed(() => {
  if (!source.value || running.value) return false
  if (task.value === 'vqa' && !question.value.trim()) return false
  return true
})

const runHint = computed(() => {
  if (source.value?.kind === 'pdf') return 'PDF 将按页渲染后并发解析，页数越多耗时越长'
  if (task.value === 'kie') return '留空字段名时模型会自动归纳关键信息'
  if (task.value === 'vqa') return '答案保持简洁，适合发票、证件、票据类提问'
  if (mode.value === 'region') return '区域模式会先做版面检测，适合印刷体文档'
  return '整页模式保留阅读顺序，适合手写、书法与不规则排版'
})

const kindLabel = computed(() => (source.value?.kind === 'pdf' ? 'PDF 文档' : '图片'))

function setTask(next: TaskKind): void {
  task.value = next
  if (source.value?.kind === 'pdf') task.value = 'document'
}

function onPick(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void handleFile(file)
}

async function handleFile(file: File): Promise<void> {
  try {
    assertSize(file)
    if (file.type.startsWith('video/')) throw new Error('请上传图片或 PDF 文档')
    if (isPdf(file)) {
      if (!pdfReady.value) throw new Error('当前服务未安装 pypdfium2，PDF 解析不可用')
      const dataUrl = await readAsDataUrl(file)
      source.value = { kind: 'pdf', name: file.name, size: file.size, dataUrl, thumb: '' }
      task.value = 'document'
      toast.success('PDF 已载入，将按页解析')
      return
    }
    if (!file.type.startsWith('image/') && !/\.(png|jpe?g|webp|bmp|gif)$/i.test(file.name)) {
      throw new Error('仅支持 JPG / PNG / WEBP / PDF')
    }
    const { dataUrl, thumb } = await prepareImage(file)
    source.value = { kind: 'image', name: file.name, size: file.size, dataUrl, thumb }
    if (task.value === 'document' && mode.value === 'region' && !regionReady.value) mode.value = 'page'
    toast.success('图片已就绪')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '文件读取失败')
  }
}

async function loadSample(item: SampleItem): Promise<void> {
  try {
    const response = await fetch(item.url)
    if (!response.ok) throw new Error('示例加载失败')
    const blob = await response.blob()
    const extension = item.name.split('.').pop() ?? 'jpg'
    await handleFile(new File([blob], item.name, { type: blob.type || `image/${extension}` }))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '示例加载失败')
  }
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void handleFile(file)
}

function onPaste(event: ClipboardEvent): void {
  const item = Array.from(event.clipboardData?.items ?? []).find((entry) => entry.type.startsWith('image/'))
  const file = item?.getAsFile()
  if (file) {
    void handleFile(file)
    toast.info('已从剪贴板读取图片')
  }
}

function clearSource(): void {
  source.value = null
  result.value = null
  error.value = ''
  elapsed.value = 0
}

function parseFields(): string[] {
  return fieldsText.value
    .split(/[,，\n;；]/)
    .map((field) => field.trim())
    .filter(Boolean)
    .slice(0, 20)
}

async function run(): Promise<void> {
  if (!source.value || running.value) return
  error.value = ''
  result.value = null
  running.value = true
  startedAt = performance.now()
  elapsed.value = 0
  ticker = window.setInterval(() => {
    elapsed.value = performance.now() - startedAt
  }, 200)

  try {
    const current = source.value
    let output: RunResult
    if (current.kind === 'pdf') {
      output = await runPdf({
        pdf: current.dataUrl,
        mode: mode.value,
        max_pages: maxPages.value,
        dpi: dpi.value,
        max_tokens: maxTokens.value,
      })
    } else if (task.value === 'kie') {
      output = await runKie({ image: current.dataUrl, fields: parseFields(), max_tokens: maxTokens.value })
    } else if (task.value === 'vqa') {
      output = await runVqa({ image: current.dataUrl, question: question.value.trim() })
    } else {
      output = await runOcr({ image: current.dataUrl, mode: mode.value, max_tokens: maxTokens.value })
    }
    result.value = output
    history.add({
      kind: current.kind === 'pdf' ? 'document' : task.value,
      source: current.kind,
      title: history.titleFor(current.kind === 'pdf' ? 'document' : task.value, output),
      mode: mode.value,
      elapsedMs: output.elapsedMs,
      text: history.excerptFor(output),
      thumb: current.thumb,
      meta: {
        文件: current.name,
        模式: mode.value === 'region' ? '区域' : '整页',
        耗时: `${(output.elapsedMs / 1000).toFixed(1)}s`,
      },
      result: output,
    })
    toast.success('解析完成')
    if (window.innerWidth < 860) {
      requestAnimationFrame(() => document.querySelector('.result-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '解析失败'
    toast.error(error.value)
  } finally {
    running.value = false
    if (ticker !== null) {
      window.clearInterval(ticker)
      ticker = null
    }
  }
}

onMounted(async () => {
  window.addEventListener('paste', onPaste)
  try {
    const data = await getSamples()
    samples.value = data.items.slice(0, 6)
  } catch {
    /* samples are a convenience only */
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('paste', onPaste)
  if (ticker !== null) window.clearInterval(ticker)
})
</script>

<template>
  <div class="page">
    <section class="hero">
      <div>
        <h1>把图片读成<em>可编辑的结构化内容</em></h1>
        <p>
          基于 Xiaomi-OCR-0（0.8B 统一文档解析模型）的本地工作台：整页 / 区域 Markdown 解析、关键信息抽取与图文问答，
          推理全程在本机完成。
        </p>
      </div>
      <div class="hero-badges">
        <span class="pill pill-brand"><AppIcon name="zap" :size="12" />本地推理</span>
        <span class="pill">表格 · 公式 · 手写</span>
        <span class="pill">移动端适配</span>
      </div>
    </section>

    <div class="workspace">
      <section class="card">
        <div class="card-head">
          <div class="card-title">输入</div>
          <span class="card-hint">{{ kindLabel }}</span>
          <div style="margin-left: auto; display: flex; gap: 6px">
            <button class="icon-mini" title="相册 / 文件" @click="fileInput?.click()"><AppIcon name="image" :size="15" /></button>
            <button class="icon-mini" title="拍照" @click="cameraInput?.click()"><AppIcon name="camera" :size="15" /></button>
          </div>
        </div>

        <div class="card-body" style="display: flex; flex-direction: column; gap: 14px">
          <div class="mode-grid">
            <button
              v-for="item in tasks"
              :key="item.id"
              class="mode-tile"
              :class="{ active: task === item.id }"
              :disabled="source?.kind === 'pdf' && item.id !== 'document'"
              @click="setTask(item.id)"
            >
              <span class="mode-name"><AppIcon :name="item.icon" :size="15" />{{ item.label }}</span>
              <span class="mode-desc">{{ item.desc }}</span>
            </button>
          </div>

          <div
            class="dropzone"
            :class="{ dragging, 'has-preview': source }"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <input ref="fileInput" type="file" accept="image/*,application/pdf" @change="onPick" />
            <template v-if="!source">
              <div class="dropzone-inner">
                <div class="dropzone-icon"><AppIcon name="upload" :size="24" /></div>
                <div class="dropzone-title">拖拽图片 / PDF 到这里</div>
                <div class="dropzone-hint">或点击选择文件 · 支持 Ctrl+V 粘贴截图<br />JPG / PNG / WEBP / PDF，最大 30MB</div>
              </div>
            </template>
            <template v-else>
              <div class="preview-wrap">
                <img v-if="source.kind === 'image'" :src="source.dataUrl" :alt="source.name" />
                <div v-else class="pdf-cover">
                  <AppIcon name="file" :size="52" :stroke-width="1.2" />
                  <strong style="font-size: 14px">{{ source.name }}</strong>
                  <span style="font-size: 12px; opacity: 0.7">PDF · 将按页解析</span>
                </div>
                <div class="preview-bar">
                  <AppIcon name="image" :size="13" />
                  <span class="name">{{ source.name }}</span>
                  <span class="spacer" />
                  <button title="移除" @click.stop="clearSource"><AppIcon name="close" :size="15" /></button>
                </div>
              </div>
            </template>
          </div>

          <div class="sample-row" v-if="samples.length">
            <span class="label">试试示例</span>
            <button
              v-for="item in samples"
              :key="item.name"
              class="chip"
              :class="{ active: source?.name === item.name }"
              @click="loadSample(item)"
            >
              <AppIcon name="image" :size="12" />{{ item.label }}
            </button>
          </div>

          <div v-if="task === 'kie'" class="field">
            <label>抽取字段（可选，用逗号或换行分隔）</label>
            <textarea
              v-model="fieldsText"
              class="textarea"
              rows="2"
              placeholder="例如：商户名称, 总金额, 日期, 发票号码"
            />
            <div class="sample-row" style="padding-top: 2px">
              <button class="chip" @click="fieldsText = '商户名称, 总金额, 日期, 商品明细'">收据</button>
              <button class="chip" @click="fieldsText = '姓名, 证件号码, 有效期, 签发机关'">证件</button>
              <button class="chip" @click="fieldsText = '发票代码, 发票号码, 购买方, 金额, 税额'">发票</button>
            </div>
          </div>

          <div v-if="task === 'vqa'" class="field">
            <label>你的问题</label>
            <textarea
              v-model="question"
              class="textarea"
              rows="2"
              placeholder="例如：这张小票的总金额是多少？"
              @keydown.ctrl.enter="run"
            />
            <div class="sample-row" style="padding-top: 2px">
              <button class="chip" @click="question = '这张小票的总金额是多少？'">总金额</button>
              <button class="chip" @click="question = '文档的标题是什么？'">文档标题</button>
              <button class="chip" @click="question = '票据的开具日期是哪天？'">日期</button>
            </div>
          </div>

          <div class="option-grid">
            <div class="field">
              <label>解析模式</label>
              <div class="segmented" style="width: 100%">
                <button style="flex: 1" :class="{ active: mode === 'page' }" @click="mode = 'page'">整页</button>
                <button
                  style="flex: 1"
                  :class="{ active: mode === 'region' }"
                  :disabled="!regionReady"
                  :title="regionReady ? '先做版面检测再逐区域识别' : '需要本地 PP-DocLayoutV3 版面模型权重'"
                  @click="mode = 'region'"
                >
                  区域
                </button>
              </div>
            </div>
            <div class="field" v-if="source?.kind === 'pdf'">
              <label>最多解析页数</label>
              <div class="option-row">
                <span>按页渲染</span>
                <select v-model.number="maxPages">
                  <option :value="1">1 页</option>
                  <option :value="2">2 页</option>
                  <option :value="3">3 页</option>
                  <option :value="5">5 页</option>
                  <option :value="10">10 页</option>
                </select>
              </div>
            </div>
            <div class="field" v-else>
              <label>输出上限</label>
              <div class="option-row">
                <span>越大越慢</span>
                <select v-model.number="maxTokens">
                  <option :value="1024">1024 tokens</option>
                  <option :value="2048">2048 tokens · 推荐</option>
                  <option :value="4096">4096 tokens · 长文档</option>
                </select>
              </div>
            </div>
          </div>

          <div v-if="healthState.health && !regionReady" class="warn-banner">
            <AppIcon name="info" :size="15" />
            <span>{{ healthState.health.regionHint }}</span>
          </div>
          <div v-if="healthState.health && !healthState.health.modelOnline" class="warn-banner">
            <AppIcon name="alert" :size="15" />
            <span>本地模型未连接（{{ healthState.health.endpoint }}）。请先启动 Ollama 或 SGLang / vLLM 服务。</span>
          </div>

          <div class="run-bar">
            <button class="btn btn-primary" style="flex: 1" :disabled="!canRun" @click="run">
              <span v-if="running" class="spinner" />
              <AppIcon v-else name="scan" :size="17" />
              {{ running ? `解析中 · ${(elapsed / 1000).toFixed(0)}s` : '开始识别' }}
            </button>
            <button class="btn btn-ghost" :disabled="!source || running" @click="clearSource">
              <AppIcon name="trash" :size="16" />清空
            </button>
          </div>
          <p class="card-hint" style="margin: 0">{{ runHint }}</p>
        </div>
      </section>

      <section>
        <div v-if="running" class="card result-card">
          <div class="card-head">
            <div class="card-title">识别结果</div>
            <span class="pill pill-brand"><span class="dot dot-pulse" />推理中</span>
          </div>
          <div class="loading-panel">
            <div class="orb" />
            <h3>{{ task === 'vqa' ? '正在阅读图像并组织答案' : task === 'kie' ? '正在抽取关键信息' : '正在解析文档版面' }}</h3>
            <p>{{ runHint }}<br />已用时 {{ (elapsed / 1000).toFixed(1) }} 秒，本地 CPU 推理通常需要数十秒。</p>
            <div class="progress-track" />
          </div>
        </div>

        <ResultPanel v-else-if="result" :result="result" :elapsed-ms="elapsed" @restart="clearSource" />

        <div v-else class="card result-card">
          <div class="card-head">
            <div class="card-title">识别结果</div>
            <span class="pill">等待输入</span>
          </div>
          <div class="empty-state">
            <div class="big-icon"><AppIcon name="scan" :size="30" /></div>
            <h3>上传图片或 PDF，开始结构化解析</h3>
            <p>输出保留模型原始阅读顺序与不确定内容，表格转换为 HTML、公式以 LaTeX 渲染，可一键复制或下载 Markdown。</p>
            <div class="capability-list">
              <div><strong>文档解析</strong>整页 Markdown，支持表格、公式、手写体与书法长卷</div>
              <div><strong>信息抽取</strong>按字段输出 JSON，适合票据、证件、单据</div>
              <div><strong>图文问答</strong>针对文档中的文字与数据直接提问</div>
            </div>
          </div>
        </div>

        <div v-if="error" class="error-banner" style="margin: 12px 0 0">
          <AppIcon name="alert" :size="16" />
          <span>{{ error }}</span>
        </div>
      </section>
    </div>

    <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="onPick" />
  </div>
</template>
