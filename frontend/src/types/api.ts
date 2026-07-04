/** API 类型定义 */

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  created_at: string
  kb_type: string
}

export interface KnowledgeBaseDocumentInfo {
  file_name: string
  chunks: number
  chapters: string[]
}

export interface KnowledgeBaseDocumentsResponse {
  kb_id: string
  kb_name: string
  total_chunks: number
  documents: KnowledgeBaseDocumentInfo[]
}

export interface KnowledgeBaseType {
  value: string
  label: string
}

export interface AskRequest {
  question: string
  kb_id?: string
}

export interface AskResponse {
  question: string
  answer: string
  contexts: string[]
}

export interface ConfigResponse {
  chat_provider: string
  chat_model: string
  embedding_model: string
  top_k: number
  chunk_size: number
  chunk_overlap: number
  chapter_split: boolean
  chapter_chunk_threshold: number
  chapter_chunk_overlap: number
  enable_query_expansion: boolean
}

export interface BuildResponse {
  status: string
  message: string
}

export interface HealthResponse {
  status: string
}

/** 流式问答服务端事件类型 */
export type StreamEvent =
  | { type: 'question'; question: string }
  | { type: 'contexts'; contexts: string[] }
  | { type: 'token'; token: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export interface StreamingAskCallbacks {
  onQuestion?: (question: string) => void
  onContexts?: (contexts: string[]) => void
  onToken?: (token: string) => void
  onDone?: () => void
  onError?: (message: string) => void
}

export interface CreateKnowledgeBaseRequest {
  name: string
  description?: string
  kb_type?: string
}
