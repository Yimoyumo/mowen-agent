/**
 * Markdown 渲染工具
 * 使用 marked 解析 Markdown，highlight.js 语法高亮，DOMPurify 清洗 HTML 防止 XSS。
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

// 配置 marked：开启 GFM、换行转 <br>
marked.setOptions({
  gfm: true,
  breaks: true,
})

/**
 * 将 Markdown 文本渲染为安全的 HTML。
 * 流式输出时内容可能不完整，marked 会尽量容错解析。
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''

  // 自定义 renderer：代码块加语法高亮
  const renderer = new marked.Renderer()
  renderer.code = ({ text: code, lang }: { text: string; lang?: string }) => {
    const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
    const langLabel = lang ? lang : 'text'
    try {
      const highlighted = hljs.highlight(code, { language }).value
      return `<pre data-lang="${langLabel}"><code class="hljs language-${language}">${highlighted}</code></pre>`
    } catch {
      return `<pre data-lang="${langLabel}"><code class="hljs">${code}</code></pre>`
    }
  }

  const rawHtml = marked.parse(text, { async: false, renderer }) as string
  return DOMPurify.sanitize(rawHtml, {
    ADD_ATTR: ['target', 'src', 'alt', 'title', 'class', 'data-lang'],
    ADD_TAGS: ['img'],
  })
}
