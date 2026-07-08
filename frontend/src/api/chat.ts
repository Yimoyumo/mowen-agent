/** 对话 API：流式通用对话 */

import { apiClient } from './config'
import type {
  ChatRequest,
  StreamingChatCallbacks,
} from '@/types/api'

// ==================== 通用对话 ====================

/**
 * 流式通用对话 /chat/stream
 * 支持多轮上下文，可选 RAG 增强。
 * 返回一个 abort 函数，调用后可中断连接。
 */
export function chatStream(
  messages: ChatRequest['messages'],
  kbId: string | null | undefined,
  callbacks: StreamingChatCallbacks,
  options?: {
    stream?: boolean
    showReasoning?: boolean
    uploadedFiles?: { token: string; filename: string }[]
    sessionId?: string
  },
): () => void {
  const abortController = new AbortController()

  const body: ChatRequest = {
    messages,
    kb_id: kbId ?? null,
    stream: options?.stream ?? true,
    show_reasoning: options?.showReasoning ?? false,
    uploaded_files: options?.uploadedFiles ?? undefined,
    session_id: options?.sessionId ?? undefined,
  }

  fetch(`${apiClient.defaults.baseURL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: abortController.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const errorText = await response.text()
        callbacks.onError?.(`请求失败 (${response.status}): ${errorText}`)
        return
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder('utf-8')
      if (!reader) {
        callbacks.onError?.('响应没有可读流')
        return
      }

      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue
          const payload = trimmed.slice(6)
          if (payload === '[DONE]') {
            callbacks.onDone?.()
            return
          }
          try {
            const event = JSON.parse(payload) as
              | { type: 'contexts'; contexts: string[] }
              | { type: 'reasoning'; token: string }
              | { type: 'token'; token: string; input_tokens?: number; output_tokens?: number; context_window?: number }
              | { type: 'tool_start'; tool: string; input: string }
              | { type: 'tool_end'; tool: string; output: string }
              | { type: 'done'; input_tokens?: number; output_tokens?: number; context_window?: number }
              | { type: 'error'; message: string }

            if (event.type === 'contexts') callbacks.onContexts?.(event.contexts)
            else if (event.type === 'reasoning') callbacks.onReasoning?.(event.token)
            else if (event.type === 'token') {
              callbacks.onToken?.(event.token)
              // 实时更新 token 统计
              if (event.input_tokens != null) {
                callbacks.onTokenStats?.({ input_tokens: event.input_tokens, output_tokens: event.output_tokens ?? 0, context_window: event.context_window ?? 0 })
              }
            }
            else if (event.type === 'tool_start') callbacks.onToolStart?.(event.tool, event.input)
            else if (event.type === 'tool_end') callbacks.onToolEnd?.(event.tool, event.output)
            else if (event.type === 'done') callbacks.onDone?.(event.input_tokens != null ? { input_tokens: event.input_tokens, output_tokens: event.output_tokens ?? 0, context_window: event.context_window ?? 0 } : undefined)
            else if (event.type === 'error') callbacks.onError?.(event.message)
          } catch {
            // 忽略无法解析的行
          }
        }
      }

      callbacks.onDone?.()
    })
    .catch((err: unknown) => {
      if (err instanceof Error && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : String(err)
      callbacks.onError?.(`流式请求异常: ${message}`)
    })

  return () => abortController.abort()
}
