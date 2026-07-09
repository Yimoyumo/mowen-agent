/** 用户设置 API */

import { apiClient } from './config'
import type {
  UserSettings,
  ProvidersResponse,
  ProviderInfo,
  FetchModelsResult,
  UserProfile,
  MemoryResponse,
  MemoryItem,
  EmbeddingConfig,
} from '@/types/api'

// ==================== 用户设置 ====================

export async function getSettings(): Promise<UserSettings> {
  const { data } = await apiClient.get<UserSettings>('/settings')
  return data
}

export async function updateSettings(updates: Partial<UserSettings>): Promise<UserSettings> {
  const { data } = await apiClient.put<{ status: string; settings: UserSettings }>('/settings', updates)
  return data.settings
}

export async function resetSettings(): Promise<UserSettings> {
  const { data } = await apiClient.post<{ status: string; settings: UserSettings }>('/settings/reset')
  return data.settings
}

// ==================== 厂商管理 ====================

export async function getProviders(): Promise<ProvidersResponse> {
  const { data } = await apiClient.get<ProvidersResponse>('/settings/providers')
  return data
}

export async function updateProvider(
  providerId: string,
  apiKey?: string,
  baseUrl?: string,
): Promise<void> {
  await apiClient.put(`/settings/providers/${providerId}`, {
    api_key: apiKey || '',
    base_url: baseUrl || '',
  })
}

export async function addCustomProvider(name: string, baseUrl: string, apiKey?: string): Promise<ProviderInfo> {
  const { data } = await apiClient.post<{ status: string; provider: ProviderInfo }>(
    '/settings/providers',
    { name, base_url: baseUrl, api_key: apiKey || '' },
  )
  return data.provider
}

export async function deleteCustomProvider(providerId: string): Promise<void> {
  await apiClient.delete(`/settings/providers/${providerId}`)
}

export async function fetchProviderModels(
  providerId: string,
  apiKey?: string,
): Promise<FetchModelsResult> {
  const { data } = await apiClient.post<FetchModelsResult>(
    `/settings/providers/${providerId}/fetch`,
    { api_key: apiKey || '' },
  )
  return data
}

export interface TestResult {
  ok: boolean
  latency_ms?: number
  response_preview?: string
  error?: string
}

export async function testModel(
  providerId: string,
  model: string,
): Promise<TestResult> {
  const { data } = await apiClient.post<TestResult>(
    `/settings/providers/${providerId}/test`,
    { model },
  )
  return data
}

export async function setCurrentModel(modelRef: string): Promise<void> {
  await apiClient.put('/settings/model', { model: modelRef })
}

// ==================== 向量模型 ====================

export async function getEmbeddingConfig(): Promise<EmbeddingConfig> {
  const { data } = await apiClient.get<EmbeddingConfig>('/settings/embedding')
  return data
}

export async function setEmbeddingModel(modelRef: string): Promise<void> {
  await apiClient.put('/settings/embedding', { embedding_model: modelRef })
}

export async function setEmbeddingCustom(config: {
  enabled?: boolean
  base_url?: string
  api_key?: string
  model?: string
}): Promise<void> {
  await apiClient.put('/settings/embedding/custom', config)
}

// ==================== 用户画像 ====================

export async function getProfile(): Promise<UserProfile> {
  const { data } = await apiClient.get<UserProfile>('/settings/profile')
  return data
}

export async function updateProfile(profile: UserProfile): Promise<UserProfile> {
  const { data } = await apiClient.put<{ status: string; profile: UserProfile }>(
    '/settings/profile',
    profile,
  )
  return data.profile
}

// ==================== 记忆管理 ====================

export async function getMemories(): Promise<MemoryResponse> {
  const { data } = await apiClient.get<MemoryResponse>('/memories')
  return data
}

export async function addMemory(type: string, content: string): Promise<void> {
  await apiClient.post('/memories', { type, content })
}

export async function updateMemory(id: string, type: string, content: string): Promise<void> {
  await apiClient.put(`/memories/${id}`, { type, content })
}

export async function deleteMemory(id: string): Promise<void> {
  await apiClient.delete(`/memories/${id}`)
}

export async function clearMemories(): Promise<void> {
  await apiClient.delete('/memories')
}

// ==================== MCP & Skills 扩展信息 ====================

export interface McpServerInfo {
  name: string
  command: string
  args: string[]
  transport: string
  url: string
}

export interface SkillInfo {
  name: string
  available: boolean
}

export interface ExtensionsInfo {
  mcp_servers: McpServerInfo[]
  skills: SkillInfo[]
  available_skills: string[]
}

export async function getExtensions(): Promise<ExtensionsInfo> {
  const { data } = await apiClient.get<ExtensionsInfo>('/settings/extensions')
  return data
}

// ==================== MCP 服务器管理 ====================

export async function addMcpServer(server: {
  name: string
  command?: string
  args?: string[]
  transport?: string
  url?: string
}): Promise<void> {
  await apiClient.post('/settings/mcp-servers', server)
}

export async function updateMcpServer(
  name: string,
  updates: {
    command?: string
    args?: string[]
    transport?: string
    url?: string
  },
): Promise<void> {
  await apiClient.put(`/settings/mcp-servers/${name}`, updates)
}

export async function deleteMcpServer(name: string): Promise<void> {
  await apiClient.delete(`/settings/mcp-servers/${name}`)
}

export interface McpTestResult {
  ok: boolean
  tool_count: number
  error: string
}

export async function testMcpServers(): Promise<Record<string, McpTestResult>> {
  const { data } = await apiClient.post<{ results: Record<string, McpTestResult> }>('/settings/mcp-servers/test')
  return data.results
}

// ==================== Agent 工具配置 ====================

export interface AgentSettings {
  tavily_api_key: string
}

export async function getAgentSettings(): Promise<AgentSettings> {
  const { data } = await apiClient.get<AgentSettings>('/settings/agent')
  return data
}

export async function updateAgentSettings(tavilyApiKey: string): Promise<void> {
  await apiClient.put('/settings/agent', { tavily_api_key: tavilyApiKey })
}
