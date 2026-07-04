/**
 * Markdown 渲染工具
 * 使用 marked 解析 Markdown，DOMPurify 清洗 HTML 防止 XSS。
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked：开启 GFM、换行转 <br>、代码高亮占位
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
  const rawHtml = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(rawHtml, {
    ADD_ATTR: ['target'],
  })
}
