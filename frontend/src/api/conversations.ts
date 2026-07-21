/** 对话历史 API：会话和消息的 CRUD + 批量同步 */

import { apiClient } from './config'
import type { ChatMessage, Conversation } from '@/types/api'

// ==================== 会话操作 ====================

/** 列出所有会话（不含消息）。
 *  @param since 可选时间戳（毫秒），只返回 updatedAt > since 的会话（增量同步）
 */
export async function listConversations(since?: number): Promise<Conversation[]> {
  const params = since ? { since } : {}
  const { data } = await apiClient.get('/conversations', { params })
  return data.conversations ?? []
}

/** 获取单个会话（含全部消息） */
export async function getConversation(id: string): Promise<Conversation | null> {
  try {
    const { data } = await apiClient.get(`/conversations/${id}`)
    return data
  } catch {
    return null
  }
}

/** 创建新会话 */
export async function createConversation(conv: {
  id: string
  title?: string
  kbId?: string | null
  createdAt?: number
  updatedAt?: number
}): Promise<void> {
  await apiClient.post('/conversations', conv)
}

/** 更新会话（标题/kb） */
export async function updateConversation(id: string, updates: {
  title?: string
  kbId?: string | null
}): Promise<void> {
  await apiClient.put(`/conversations/${id}`, updates)
}

/** 删除会话 */
export async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`/conversations/${id}`)
}

/** 清空所有会话 */
export async function deleteAllConversations(): Promise<void> {
  await apiClient.delete('/conversations')
}

// ==================== 消息操作 ====================

/** 添加消息 */
export async function addMessage(convId: string, msg: ChatMessage): Promise<void> {
  await apiClient.post(`/conversations/${convId}/messages`, msg)
}

/** 更新消息 */
export async function updateMessage(
  convId: string,
  msgId: string,
  updates: Partial<ChatMessage>,
): Promise<void> {
  await apiClient.put(`/conversations/${convId}/messages/${msgId}`, updates)
}

/** 删除消息 */
export async function deleteMessage(convId: string, msgId: string): Promise<void> {
  await apiClient.delete(`/conversations/${convId}/messages/${msgId}`)
}

// ==================== 批量同步 ====================

/** 批量同步：从前端 localStorage 导入所有会话和消息 */
export async function syncConversations(conversations: Conversation[]): Promise<{
  synced_conversations: number
  synced_messages: number
}> {
  const { data } = await apiClient.post('/conversations/sync', { conversations })
  return data
}
