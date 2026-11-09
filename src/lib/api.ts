import type { DocMode, Health, RunResult, SampleItem } from './types'

const BASE = '/api'

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, init)
  } catch {
    throw new ApiError('无法连接本地服务，请确认已启动 API 服务（npm run server）', 0)
  }
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const data = (await response.json()) as { detail?: unknown }
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) detail = '请求参数不合法'
    } catch {
      /* keep default message */
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getHealth(): Promise<Health> {
  return request<Health>('/health')
}

export function getSamples(): Promise<{ items: SampleItem[] }> {
  return request<{ items: SampleItem[] }>('/samples')
}

export function runOcr(payload: { image: string; mode: DocMode; max_tokens: number }): Promise<RunResult> {
  return post<RunResult>('/ocr', payload)
}

export function runKie(payload: { image: string; fields: string[]; max_tokens: number }): Promise<RunResult> {
  return post<RunResult>('/kie', payload)
}

export function runVqa(payload: { image: string; question: string }): Promise<RunResult> {
  return post<RunResult>('/vqa', payload)
}

export function runPdf(payload: {
  pdf: string
  mode: DocMode
  max_pages: number
  dpi: number
  max_tokens: number
}): Promise<RunResult> {
  return post<RunResult>('/pdf', payload)
}

export { ApiError }
