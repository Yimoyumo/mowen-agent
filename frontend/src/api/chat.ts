import { apiClient } from './config'
import type {
  AskRequest,
  AskResponse,
  ConfigResponse,
  BuildResponse,
  HealthResponse,
  KnowledgeBase,
  KnowledgeBaseDocumentsResponse,
  KnowledgeBaseType,
  StreamingAskCallbacks,
  CreateKnowledgeBaseRequest,
} from '@/types/api'

export async function healthCheck(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health')
  return data
}

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get<ConfigResponse>('/config')
  return data
}

export async function askQuestion(
  question: string,
  kbId?: string,
): Promise<AskResponse> {
  const { data } = await apiClient.post<AskResponse>('/ask', { question, kb_id: kbId } satisfies AskRequest)
  return data
}

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  const { data } = await apiClient.get<KnowledgeBase[]>('/knowledge-bases')
  return data
}

export async function getKnowledgeBaseTypes(): Promise<KnowledgeBaseType[]> {
  const { data } = await apiClient.get<{ types: KnowledgeBaseType[] }>('/knowledge-base-types')
  return data.types
}

export async function createKnowledgeBase(
  payload: CreateKnowledgeBaseRequest,
): Promise<KnowledgeBase> {
  const { data } = await apiClient.post<KnowledgeBase>('/knowledge-bases', payload)
  return data
}

export async function deleteKnowledgeBase(kbId: string): Promise<BuildResponse> {
  const { data } = await apiClient.delete<BuildResponse>(`/knowledge-bases/${kbId}`)
  return data
}

export async function buildKnowledgeBase(kbId: string): Promise<BuildResponse> {
  const { data } = await apiClient.post<BuildResponse>(`/knowledge-bases/${kbId}/build`)
  return data
}

export async function getKnowledgeBaseDocuments(
  kbId: string,
): Promise<KnowledgeBaseDocumentsResponse> {
  const { data } = await apiClient.get<KnowledgeBaseDocumentsResponse>(`/knowledge-bases/${kbId}/documents`)
  return data
}

export async function uploadDocumentToKnowledgeBase(
  kbId: string,
  file: File,
): Promise<BuildResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<BuildResponse>(
    `/knowledge-bases/${kbId}/upload`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return data
}

/**
 * 流式请求 /ask/stream，通过回调逐块消费数据。
 * 返回一个 abort 函数，调用后可中断连接。
 */
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
