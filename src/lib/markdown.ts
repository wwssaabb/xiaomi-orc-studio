import MarkdownIt from 'markdown-it'
import katex from 'katex'
import DOMPurify from 'dompurify'
import 'katex/dist/katex.min.css'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
  typographer: false,
})

const defaultLinkOpen =
  md.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx]?.attrSet('target', '_blank')
  tokens[idx]?.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

function renderMath(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: false,
      strict: 'ignore',
      output: 'htmlAndMathml',
    })
  } catch {
    return `<code>${escapeHtml(tex)}</code>`
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const OPEN = '\uE000'
const CLOSE = '\uE001'

function protectMath(source: string): { text: string; blocks: string[] } {
  const blocks: string[] = []
  const text = source.replace(/\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g, (match, displayTex, inlineTex) => {
    const isDisplay = typeof displayTex === 'string'
    const tex = String(isDisplay ? displayTex : inlineTex).trim()
    if (!tex) return match
    blocks.push(renderMath(tex, isDisplay))
    return `${OPEN}${blocks.length - 1}${CLOSE}`
  })
  return { text, blocks }
}

export function renderMarkdown(source: string): string {
  if (!source) return ''
  const { text, blocks } = protectMath(source)
  let html = md.render(text)
  html = html.replace(/\uE000(\d+)\uE001/g, (_match, index: string) => blocks[Number(index)] ?? '')
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mtable', 'mtr', 'mtd', 'semantics', 'annotation'],
    ADD_ATTR: ['style', 'class', 'xmlns', 'encoding', 'display'],
    FORBID_TAGS: ['style', 'iframe', 'form', 'input'],
  })
}

export function markdownToPlain(source: string): string {
  return source
    .replace(/<[^>]+>/g, ' ')
    .replace(/\$\$?/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}
