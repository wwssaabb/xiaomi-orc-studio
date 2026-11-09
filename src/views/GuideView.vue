<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { useHealth } from '../lib/health'
import { formatDuration } from '../lib/format'

const { state, refresh } = useHealth()

const health = computed(() => state.health)

const capabilityRows = computed(() => {
  const capabilities = health.value?.capabilities
  return [
    { key: 'page', label: '整页解析', ok: capabilities?.page ?? false },
    { key: 'region', label: '区域解析（版面检测）', ok: capabilities?.region ?? false },
    { key: 'kie', label: '关键信息抽取', ok: capabilities?.kie ?? false },
    { key: 'vqa', label: 'OCR 图文问答', ok: capabilities?.vqa ?? false },
    { key: 'pdf', label: 'PDF 解析', ok: capabilities?.pdf ?? false },
  ]
})

onMounted(() => {
  if (!state.health) void refresh()
})
</script>

<template>
  <div class="page">
    <section class="hero" style="padding-bottom: 16px">
      <div>
        <h1>使用指南</h1>
        <p>Xiaomi-OCR-Studio 是 Xiaomi-OCR-0 的本地浏览器工作台。模型与数据都留在你的电脑上，页面只与 127.0.0.1 上的服务通信。</p>
      </div>
      <div class="hero-badges">
        <RouterLink class="btn btn-primary" style="min-height: 38px" to="/">开始解析</RouterLink>
      </div>
    </section>

    <div class="guide-grid">
      <section class="card guide-card">
        <h3><AppIcon name="zap" :size="17" />运行状态</h3>
        <div class="stat-grid">
          <div class="stat">
            <div class="stat-label">推理后端</div>
            <div class="stat-value">{{ health?.backend ?? '—' }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">模型</div>
            <div class="stat-value" style="font-size: 12.5px">{{ health?.model ?? '—' }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">模型服务</div>
            <div class="stat-value">
              <span :class="health?.modelOnline ? 'pill pill-success' : 'pill pill-danger'">
                <span class="dot" />{{ health?.modelOnline ? '已连接' : '未连接' }}
              </span>
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">最近检测</div>
            <div class="stat-value" style="font-size: 12.5px">
              {{ state.lastChecked ? new Date(state.lastChecked).toLocaleTimeString() : '—' }}
            </div>
          </div>
        </div>
        <div style="font-size: 12px; color: var(--muted); word-break: break-all">
          推理地址：{{ health?.endpoint ?? '—' }}
        </div>
        <div style="display: flex; flex-direction: column; gap: 6px">
          <div v-for="row in capabilityRows" :key="row.key" class="option-row">
            <span>{{ row.label }}</span>
            <span :class="row.ok ? 'pill pill-success' : 'pill'">
              <span class="dot" />{{ row.ok ? '可用' : '不可用' }}
            </span>
          </div>
        </div>
        <button class="btn btn-ghost" @click="refresh">
          <span v-if="state.loading" class="spinner" style="width: 14px; height: 14px" />
          <AppIcon v-else name="refresh" :size="15" />重新检测
        </button>
      </section>

      <section class="card guide-card">
        <h3><AppIcon name="file" :size="17" />启动本地服务</h3>
        <p>页面需要 API 服务与模型服务同时在线。若只是体验界面，可跳过模型启动，模型离线时会有明确提示。</p>
        <ul>
          <li><code>npm run server</code> 启动本项目 API（端口 8787）</li>
          <li><code>ollama serve</code> 启动 Ollama（端口 11434）</li>
          <li><code>ollama pull longwayxu/xiaomi-ocr-0:bf16</code> 首次准备模型</li>
          <li><code>npm run dev</code> 启动前端（端口 5173）</li>
        </ul>
        <p>生产模式：<code>npm run build</code> 后由 API 服务直接托管 <code>dist/</code>，手机与电脑访问同一局域网地址即可。</p>
        <div class="option-row">
          <span>当前引擎加载</span>
          <span :class="health?.engineReady ? 'pill pill-success' : 'pill pill-danger'">
            {{ health?.engineReady ? '正常' : '异常' }}
          </span>
        </div>
        <div v-if="health?.engineError" class="error-banner" style="margin: 0">{{ health.engineError }}</div>
      </section>

      <section class="card guide-card">
        <h3><AppIcon name="layout" :size="17" />模式怎么选</h3>
        <p>两种模式对应 Xiaomi-OCR-0 的两种解析流水线，准确率差异主要来自版面切分。</p>
        <ul>
          <li><strong>整页解析</strong>：模型一次读完整页，保留阅读顺序。适合手写笔记、书法、古籍、海报、不规则排版。</li>
          <li><strong>区域解析</strong>：先用 PP-DocLayoutV3 检测版面，再并发识别每个区块。适合印刷体文档、论文、报表。</li>
          <li>区域模式需要额外安装 <code>paddlex[cv]</code> 与版面模型；未安装时按钮自动禁用，页面会给出提示，不会用整页结果冒充区域结果。</li>
        </ul>
      </section>

      <section class="card guide-card">
        <h3><AppIcon name="extract" :size="17" />能力边界</h3>
        <ul>
          <li><strong>输出格式</strong>：Markdown；表格输出为 HTML 表格（OTSL 转换），公式使用 LaTeX 并在页面渲染。</li>
          <li><strong>信息抽取</strong>：字段名可留空；模型按 JSON 模式输出，缺失字段为空字符串。</li>
          <li><strong>图文问答</strong>：答案保持简短，适合“总金额是多少”这类抽取式问题，不适合需要推理的长回答。</li>
          <li><strong>PDF</strong>：逐页渲染为图片后解析，页数、DPI 都会影响耗时与显存/内存占用。</li>
          <li>服务不会补写无法辨认的内容，页面保留模型给出的不确定性。</li>
        </ul>
      </section>

      <section class="card guide-card">
        <h3><AppIcon name="camera" :size="17" />移动端使用</h3>
        <ul>
          <li>工作台右上角相机按钮会直接调起手机后置摄像头，拍照即可识别。</li>
          <li>图片会在浏览器内压缩到最长边 2048px 再上传，节省移动流量与模型 token。</li>
          <li>底部标签栏在手机上切换工作台 / 历史 / 指南；所有按钮触控高度不小于 40px。</li>
          <li>结果支持一键复制、下载，历史记录保存在本机浏览器。</li>
        </ul>
      </section>

      <section class="card guide-card">
        <h3><AppIcon name="clock" :size="17" />性能参考</h3>
        <p>本机为 CPU 推理，实测一张 A5 小票整页解析约 20 秒（300 tokens 输出）。更长输出、PDF 多页会线性增加耗时。</p>
        <div class="stat-grid">
          <div class="stat">
            <div class="stat-label">示例耗时</div>
            <div class="stat-value">{{ formatDuration(20800) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">模型规格</div>
            <div class="stat-value">0.8B · BF16</div>
          </div>
        </div>
        <p>若需更快速度或更高精度，可将后端切换到 SGLang / vLLM 并修改 <code>XIAOMI_OCR_LOCAL_URL</code> 与 <code>XIAOMI_OCR_MODEL</code>。</p>
      </section>
    </div>
  </div>
</template>
