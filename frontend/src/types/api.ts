/** API 类型定义 */

// ==================== 通用对话类型 ====================

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string           // 模型推理过程
  contexts?: string[]
  segments?: MessageSegment[]  // 交错文本和工具调用片段
  files?: { filename: string; token: string; is_image?: boolean }[]  // 用户上传的文件列表
  createdAt: number
}

export type ToolSegmentStatus =
  | 'running'
  | 'done'
  | 'waiting_approval'
  | 'waiting_answer'
  | 'denied'
  | 'timeout'
  | 'killed'

export interface ToolSegment {
  type: 'tool'
  tool: string
  input?: string
  output?: string
  status: ToolSegmentStatus
  /** 关联的交互请求 ID（审批 / 提问） */
  requestId?: string
  /** 风险等级（如 "ask"） */
  risk?: string
  /** 宿主操作 ID，用于关联 exec_update 事件 */
  opId?: string
}

export type MessageSegment =
  | { type: 'text'; content: string }
  | ToolSegment

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
  uploaded_files?: { token: string; filename: string; is_image?: boolean }[]  // 上传的文件
  session_id?: string | null   // 会话 ID，用于沙盒跨消息持久化
}

// ==================== 知识库类型 ====================

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  created_at: string
  kb_type: string
  embedding_model: string
  embedding_dim: number
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
  has_vision: boolean
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
  | { type: 'interaction_request'; request_id: string; kind: InteractionKind; session_id: string; timeout?: number; payload: InteractionRequestPayload }
  | { type: 'interaction_result'; request_id: string; status: InteractionResultStatus; approved?: boolean; answer?: string; scope?: InteractionAnswerScope }
  | { type: 'exec_update'; op_id: string; status: ExecStatus; elapsed?: number; output_tail?: string }

export interface StreamingChatCallbacks {
  onContexts?: (contexts: string[]) => void
  onReasoning?: (token: string) => void
  onToken?: (token: string) => void
  onTokenStats?: (stats: { input_tokens: number; output_tokens: number; context_window: number }) => void
  onToolStart?: (tool: string, input: string) => void
  onToolEnd?: (tool: string, output: string) => void
  onDone?: (stats?: { input_tokens: number; output_tokens: number; context_window: number }) => void
  onError?: (message: string) => void
  onInteractionRequest?: (request: InteractionRequest) => void
  onInteractionResult?: (result: InteractionResultEvent) => void
  onExecUpdate?: (update: ExecUpdateEvent) => void
}

// ==================== 交互（HITL）类型 ====================
// 统一承载"权限审批"与"ask_user 主动提问"两类交互请求，
// 后端通过 SSE 推送，前端借此渲染 InteractionCard。

export type InteractionKind = 'approval' | 'ask_user'

export type InteractionAnswerScope = 'once' | 'session' | 'always'

export type InteractionResultStatus = 'answered' | 'timeout' | 'denied'

export interface InteractionRequestPayload {
  /** 审批：关联的工具名 */
  tool?: string
  /** 审批：待执行的命令 */
  command?: string
  /** 审批：请求原因 */
  reason?: string
  /** 审批：风险等级 */
  risk?: string
  /** ask_user：问题内容 */
  question?: string
  /** ask_user：预设选项 */
  options?: string[]
  /** ask_user：是否多选 */
  multi_select?: boolean
  /** ask_user：是否允许自由输入 */
  allow_free_text?: boolean
  /** 超时秒数（有的请求会带在 payload 里） */
  timeout?: number
}

export interface InteractionRequest {
  request_id: string
  kind: InteractionKind
  session_id: string
  timeout: number
  payload: InteractionRequestPayload
  created_at?: number
}

export interface InteractionResultEvent {
  request_id: string
  status: InteractionResultStatus
  approved?: boolean
  answer?: string
  scope?: InteractionAnswerScope
}

export interface AnswerInteractionPayload {
  approved?: boolean
  scope?: InteractionAnswerScope
  answer?: string
}

export interface PendingInteractionsResult {
  requests: InteractionRequest[]
}

// ==================== 宿主执行（HostOps）类型 ====================

export type ExecStatus = 'running' | 'succeeded' | 'failed' | 'timeout' | 'killed'

export interface ExecUpdateEvent {
  op_id: string
  status: ExecStatus
  elapsed?: number
  output_tail?: string
}

export interface HostRunningOp {
  op_id: string
  command: string
  session_id: string
  started_at: number | string
}

export interface HostOp {
  op_id: string
  tool: string
  kind: string
  target: string
  risk: string
  status: ExecStatus
  exit_code?: number | null
  created_at: number | string
  finished_at?: number | string | null
}

export interface HostOpsResult {
  mode: string
  running: HostRunningOp[]
  ops: HostOp[]
}

export interface HostWorkspaceEntry {
  name: string
  type: 'file' | 'dir'
  size?: number
}

export interface HostWorkspaceResult {
  entries: HostWorkspaceEntry[]
}

// ==================== 执行器设置 ====================

export type ExecutorMode = 'host' | 'sandbox'

export type ApprovalMode = 'ask_dangerous' | 'auto' | 'ask_all'

export interface ExecutorSettingsConfig {
  /** 执行模式：host 宿主机直操 / sandbox Docker 沙盒 */
  mode: ExecutorMode
  /** 审批模式 */
  approval_mode: ApprovalMode
  /** 审批超时秒数 */
  approval_timeout: number
  /** ask_user 提问超时秒数 */
  ask_timeout: number
  /** 命令超时秒数 */
  command_timeout: number
  /** 工作区保留天数 */
  workspace_retention_days: number
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
    temperature?: number | null
    max_tokens?: number | null
    thinking?: boolean
    reasoning_effort?: string | null
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
  mcp_servers?: Record<string, unknown>
  executor?: ExecutorSettingsConfig
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

// ==================== 向量模型配置 ====================

export interface EmbeddingModelOption {
  provider_id: string
  provider_name: string
  model: string
  ref: string               // "provider/model"
  has_api_key: boolean
}

export interface EmbeddingCustom {
  enabled: boolean
  base_url: string
  api_key: string
  model: string
  has_api_key: boolean
}

export interface EmbeddingConfig {
  embedding_model: string   // 当前选中的 "provider/model"，空字符串表示自动推断
  available_models: EmbeddingModelOption[]
  embedding_custom: EmbeddingCustom
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

// ==================== 定时任务类型 ====================

export type ScheduleType = 'cron' | 'interval' | 'once'
export type TaskStatus = 'active' | 'paused' | 'completed' | 'error'

export interface ScheduleConfig {
  expression?: string      // cron: "0 9 * * *"
  seconds?: number          // interval: 3600
  datetime?: string        // once: "2024-12-25T09:00:00"
}

export interface ScheduledTask {
  id: string
  name: string
  prompt: string
  schedule_type: ScheduleType
  schedule_config: ScheduleConfig
  kb_id?: string | null
  status: TaskStatus
  last_run_at: number | null
  next_run_at: number | null
  last_result: string
  run_count: number
  created_at: number
  updated_at: number
}
