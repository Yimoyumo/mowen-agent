/** 配置与健康检查 API */

import { apiClient } from './config'
import type { ConfigResponse, HealthResponse, ModelContextInfo } from '@/types/api'

export async function healthCheck(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health')
  return data
}

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get<ConfigResponse>('/config')
  return data
}

export async function get_model_context(modelRef?: string): Promise<ModelContextInfo> {
  const params = modelRef ? { model: modelRef } : {}
  const { data } = await apiClient.get<ModelContextInfo>('/settings/model-context', { params })
  return data
}

export async function set_model_context_override(
  modelRef: string,
  overrides: {
    context_window?: number
    max_output?: number
    temperature?: number
    thinking?: boolean
    reasoning_effort?: string | null
    max_tokens?: number | null
  },
): Promise<ModelContextInfo> {
  const { data } = await apiClient.put<ModelContextInfo>(
    '/settings/model-context',
    { model: modelRef, ...overrides },
  )
  return data
}

export async function delete_model_context_override(modelRef: string): Promise<void> {
  await apiClient.delete('/settings/model-context', { params: { model: modelRef } })
}
