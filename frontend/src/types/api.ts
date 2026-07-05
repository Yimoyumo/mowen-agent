/** API 类型定义 */

// ==================== 通用对话类型 ====================

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string           // 模型推理过程
  contexts?: string[]
  segments?: MessageSegment[]  // 交错文本和工具调用片段
  createdAt: number
}

export type MessageSegment =
  | { type: 'text'; content: string }
  | { type: 'tool'; tool: string; input?: string; output?: string; status: 'running' | 'done' }

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  kbId?: string | null
  createdAt: number
  updatedAt: number
}

export interface ChatRequest {
  messages: { role: 'user' | 'assistant'; content: string }[]
  kb_id?: string | null
  stream?: boolean             // 是否流式输出，默认 true
  show_reasoning?: boolean     // 是否返回推理过程，默认 false
  uploaded_files?: { token: string; filename: string }[]  // 上传的文件
}

// ==================== 知识库类型 ====================

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

// ==================== 旧版 RAG 类型（保留兼容） ====================

export interface AskRequest {
  question: string
  kb_id?: string
}

export interface AskResponse {
  question: string
  answer: string
  contexts: string[]
}

// ==================== 配置类型 ====================

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

// ==================== 流式事件类型 ====================

export type StreamEvent =
  | { type: 'contexts'; contexts: string[] }
  | { type: 'reasoning'; token: string }
  | { type: 'token'; token: string }
  | { type: 'tool_start'; tool: string; input: string }
  | { type: 'tool_end'; tool: string; output: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export interface StreamingChatCallbacks {
  onContexts?: (contexts: string[]) => void
  onReasoning?: (token: string) => void
  onToken?: (token: string) => void
  onToolStart?: (tool: string, input: string) => void
  onToolEnd?: (tool: string, output: string) => void
  onDone?: () => void
  onError?: (message: string) => void
}

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
