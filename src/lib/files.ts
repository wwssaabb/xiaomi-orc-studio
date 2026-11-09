const MAX_UPLOAD_MB = 30

export function readAsDataUrl(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

export function assertSize(file: File, limitMb = MAX_UPLOAD_MB): void {
  if (file.size > limitMb * 1024 * 1024) {
    throw new Error(`文件体积 ${(file.size / 1024 / 1024).toFixed(1)}MB 超过 ${limitMb}MB 上限`)
  }
}

export function isPdf(file: File): boolean {
  return file.type === 'application/pdf' || /\.pdf$/i.test(file.name)
}

export function isImage(file: File): boolean {
  return file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif)$/i.test(file.name)
}

/**
 * Downscale oversized photos before upload: keeps mobile traffic low and
 * avoids spending tokens on pixels the model would discard anyway.
 */
export async function prepareImage(file: File, maxEdge = 2048, quality = 0.92): Promise<{ dataUrl: string; thumb: string }> {
  const original = await readAsDataUrl(file)
  const image = await loadImage(original)
  const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight))
  if (scale >= 1 && file.size < 1.6 * 1024 * 1024) {
    return { dataUrl: original, thumb: drawThumb(image, 240) }
  }
  const width = Math.max(1, Math.round(image.naturalWidth * scale))
  const height = Math.max(1, Math.round(image.naturalHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return { dataUrl: original, thumb: drawThumb(image, 240) }
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, width, height)
  context.imageSmoothingQuality = 'high'
  context.drawImage(image, 0, 0, width, height)
  const needsPng = /image\/png/i.test(file.type) || /\.png$/i.test(file.name)
  const dataUrl = needsPng ? canvas.toDataURL('image/png') : canvas.toDataURL('image/jpeg', quality)
  return { dataUrl, thumb: drawThumb(canvas, 240) }
}

function drawThumb(source: CanvasImageSource, edge: number): string {
  const width = (source as HTMLImageElement).naturalWidth ?? (source as HTMLCanvasElement).width
  const height = (source as HTMLImageElement).naturalHeight ?? (source as HTMLCanvasElement).height
  const scale = Math.min(1, edge / Math.max(width, height || 1))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  const context = canvas.getContext('2d')
  if (!context) return ''
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(source, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.72)
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('无法解析这张图片，请换一张试试'))
    image.src = url
  })
}

export async function downloadBlob(filename: string, content: string, mime = 'text/markdown;charset=utf-8'): Promise<void> {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    return
  } catch {
    /* fall through to legacy path (http / older mobile browsers) */
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  textarea.remove()
  if (!ok) throw new Error('当前浏览器不支持自动复制，请手动选择文本')
}
