/** 对话 API：通用对话 + 旧版 RAG 问答（保留兼容） */

import { apiClient } from './config'
import type {
  AskRequest,
  AskResponse,
  ChatRequest,
  StreamingAskCallbacks,
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
): () => void {
  const abortController = new AbortController()

  fetch(`${apiClient.defaults.baseURL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, kb_id: kbId ?? null } satisfies ChatRequest),
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
              | { type: 'token'; token: string }
              | { type: 'done' }
              | { type: 'error'; message: string }

            if (event.type === 'contexts') callbacks.onContexts?.(event.contexts)
            else if (event.type === 'token') callbacks.onToken?.(event.token)
            else if (event.type === 'done') callbacks.onDone?.()
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

// ==================== 旧版 RAG 问答（保留兼容） ====================

export async function askQuestion(
  question: string,
  kbId?: string,
): Promise<AskResponse> {
  const { data } = await apiClient.post<AskResponse>('/ask', { question, kb_id: kbId } satisfies AskRequest)
  return data
}

export function askQuestionStream(
  question: string,
  kbId: string | undefined,
  callbacks: StreamingAskCallbacks,
): () => void {
  const abortController = new AbortController()

  fetch(`${apiClient.defaults.baseURL}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, kb_id: kbId } satisfies AskRequest),
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
              | { type: 'question'; question: string }
              | { type: 'contexts'; contexts: string[] }
              | { type: 'token'; token: string }
              | { type: 'done' }
              | { type: 'error'; message: string }

            if (event.type === 'question') callbacks.onQuestion?.(event.question)
            else if (event.type === 'contexts') callbacks.onContexts?.(event.contexts)
            else if (event.type === 'token') callbacks.onToken?.(event.token)
            else if (event.type === 'done') callbacks.onDone?.()
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
