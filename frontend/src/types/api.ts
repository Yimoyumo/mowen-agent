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
  session_id?: string | null   // 会话 ID，用于沙盒跨消息持久化
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
  context_window: number
  max_output: number
  temperature: number
  max_tokens: number | null
  thinking: boolean
  reasoning_effort: string | null
}

export interface ModelContextInfo {
  model: string
  context_window: number
  max_output: number
  source?: 'override' | 'builtin' | 'unknown'
  generation_override?: {
    temperature?: number
    max_tokens?: number | null
    thinking?: boolean
    reasoning_effort?: string | null
  }
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
  | { type: 'token'; token: string; input_tokens?: number; output_tokens?: number; context_window?: number }
  | { type: 'tool_start'; tool: string; input: string }
  | { type: 'tool_end'; tool: string; output: string }
  | { type: 'done'; input_tokens?: number; output_tokens?: number; context_window?: number }
  | { type: 'error'; message: string }

export interface StreamingChatCallbacks {
  onContexts?: (contexts: string[]) => void
  onReasoning?: (token: string) => void
  onToken?: (token: string) => void
  onTokenStats?: (stats: { input_tokens: number; output_tokens: number; context_window: number }) => void
  onToolStart?: (tool: string, input: string) => void
  onToolEnd?: (tool: string, output: string) => void
  onDone?: (stats?: { input_tokens: number; output_tokens: number; context_window: number }) => void
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

// ==================== 用户设置类型 ====================

export interface UserSettings {
  model: {
    provider: string
    chat_model: string
    models_cache: Record<string, string[]>
    providers: Record<string, ProviderConfig>
  }
  retrieval: {
    top_k: number
    query_expansion: boolean | null
  }
  generation: {
    temperature: number | null
    max_tokens: number | null
  }
  persona: {
    enabled: boolean
    content: string
  }
  user_profile: {
    skills: string
    interests: string
    preferences: string
  }
  updated_at: string | null
}

export interface ProviderConfig {
  api_key: string
  base_url?: string
  name?: string
}

export interface ProviderInfo {
  id: string
  name: string
  base_url: string
  desc: string
  preset: boolean
  has_api_key: boolean
  models: string[]
}

export interface ProvidersResponse {
  providers: ProviderInfo[]
  active_model: string           // "provider/model" e.g. "deepseek/deepseek-v4-flash"
}

export interface FetchModelsResult {
  status: string
  models: string[]
  count?: number
  message?: string
}

export interface UserProfile {
  skills: string
  interests: string
  preferences: string
}

export interface MemoryItem {
  id: string
  type: string
  content: string
  created_at?: string
  hit_count?: number
  last_used?: string | null
}

export interface MemoryResponse {
  memories: MemoryItem[]
  total: number
}
