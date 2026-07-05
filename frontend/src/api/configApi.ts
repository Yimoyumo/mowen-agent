/** 配置与健康检查 API */

import { apiClient } from './config'
import type { ConfigResponse, HealthResponse } from '@/types/api'

export async function healthCheck(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health')
  return data
}

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get<ConfigResponse>('/config')
  return data
}
