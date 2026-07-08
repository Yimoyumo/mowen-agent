/** 定时任务 API */

import { apiClient } from './config'
import type { ScheduledTask } from '@/types/api'

// ==================== 定时任务 ====================

export async function listScheduledTasks(): Promise<ScheduledTask[]> {
  const { data } = await apiClient.get<{ tasks: ScheduledTask[]; total: number }>('/scheduled-tasks')
  return data.tasks
}

export async function getScheduledTask(id: string): Promise<ScheduledTask> {
  const { data } = await apiClient.get<ScheduledTask>(`/scheduled-tasks/${id}`)
  return data
}

export async function createScheduledTask(payload: {
  name: string
  prompt: string
  schedule_type: 'cron' | 'interval' | 'once'
  schedule_config: Record<string, unknown>
  kb_id?: string | null
}): Promise<ScheduledTask> {
  const { data } = await apiClient.post<ScheduledTask>('/scheduled-tasks', payload)
  return data
}

export async function updateScheduledTask(
  id: string,
  payload: Partial<{
    name: string
    prompt: string
    schedule_type: 'cron' | 'interval' | 'once'
    schedule_config: Record<string, unknown>
    kb_id: string | null
  }>,
): Promise<ScheduledTask> {
  const { data } = await apiClient.put<ScheduledTask>(`/scheduled-tasks/${id}`, payload)
  return data
}

export async function deleteScheduledTask(id: string): Promise<void> {
  await apiClient.delete(`/scheduled-tasks/${id}`)
}

export async function pauseScheduledTask(id: string): Promise<void> {
  await apiClient.post(`/scheduled-tasks/${id}/pause`)
}

export async function resumeScheduledTask(id: string): Promise<ScheduledTask> {
  const { data } = await apiClient.post<ScheduledTask>(`/scheduled-tasks/${id}/resume`)
  return data
}

export async function runScheduledTaskNow(id: string): Promise<void> {
  await apiClient.post(`/scheduled-tasks/${id}/run`)
}

export async function getScheduledTaskConversation(id: string): Promise<{
  conversation: unknown
  messages: unknown[]
}> {
  const { data } = await apiClient.get(`/scheduled-tasks/${id}/conversation`)
  return data
}
