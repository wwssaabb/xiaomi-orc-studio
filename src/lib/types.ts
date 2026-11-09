export type TaskKind = 'document' | 'kie' | 'vqa'
export type DocMode = 'page' | 'region'
export type SourceKind = 'image' | 'pdf'

export interface Capabilities {
  page: boolean
  region: boolean
  kie: boolean
  vqa: boolean
  pdf: boolean
}

export interface Health {
  ok: boolean
  backend: string
  endpoint: string
  model: string
  repo: string
  engineReady: boolean
  engineError: string | null
  modelOnline: boolean
  capabilities: Capabilities
  regionHint: string | null
}

export interface DocumentResult {
  kind: 'document'
  mode: string
  markdown: string
  pages?: number
  regions?: number
  reason?: string
  elapsedMs: number
}

export interface KieResult {
  kind: 'kie'
  json: Record<string, unknown> | null
  raw?: string
  warning?: string
  elapsedMs: number
}

export interface VqaResult {
  kind: 'vqa'
  answer: string
  question: string
  elapsedMs: number
}

export type RunResult = DocumentResult | KieResult | VqaResult

export interface HistoryItem {
  id: string
  kind: TaskKind
  source: SourceKind
  title: string
  createdAt: number
  mode?: DocMode
  elapsedMs: number
  text: string
  thumb?: string
  meta?: Record<string, string | number>
  result: RunResult
}

export interface SampleItem {
  name: string
  label: string
  url: string
}
