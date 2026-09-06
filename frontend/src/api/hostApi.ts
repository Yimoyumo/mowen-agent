/** 宿主执行 & 交互（HITL）API
 *
 * 覆盖 Agent 去沙盒化后新增的 REST 契约：
 *  - 交互（审批 / ask_user）回答与待处理列表
 *  - 宿主执行状态、取消、工作区文件树
 */

import { apiClient } from './config'
import type {
  AnswerInteractionPayload,
  HostOpsResult,
  HostWorkspaceResult,
  PendingInteractionsResult,
} from '@/types/api'

// ==================== 交互（HITL） ====================

export async function answerInteraction(
  requestId: string,
  payload: AnswerInteractionPayload,
): Promise<{ ok: boolean }> {
  const { data } = await apiClient.post<{ ok: boolean }>(`/interactions/${requestId}/answer`, payload)
  return data
}

/** 获取会话遗留的待处理交互（页面刷新后恢复卡片用） */
export async function getPendingInteractions(sessionId: string): Promise<PendingInteractionsResult> {
  const { data } = await apiClient.get<PendingInteractionsResult>('/interactions/pending', {
    params: { session_id: sessionId },
  })
  return data
}

// ==================== 宿主执行状态 ====================

/** 获取宿主执行状态（运行中进程 + 最近操作审计 + 工作区） */
export async function getHostOps(sessionId: string, limit = 50): Promise<HostOpsResult> {
  const { data } = await apiClient.get<HostOpsResult>('/host/ops', {
    params: { session_id: sessionId, limit },
  })
  return data
}

/** 取消一条宿主执行 */
export async function cancelHostOp(opId: string): Promise<{ ok: boolean }> {
  const { data } = await apiClient.post<{ ok: boolean }>(`/host/ops/${opId}/cancel`)
  return data
}

/** 获取工作区文件树 */
export async function getHostWorkspace(sessionId: string, path = ''): Promise<HostWorkspaceResult> {
  const { data } = await apiClient.get<HostWorkspaceResult>('/host/workspace', {
    params: { session_id: sessionId, path },
  })
  return data
}
