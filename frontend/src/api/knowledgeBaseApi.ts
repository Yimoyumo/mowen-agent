/** 知识库管理 API */

import { apiClient } from './config'
import type {
  BuildResponse,
  CreateKnowledgeBaseRequest,
  KnowledgeBase,
  KnowledgeBaseDocumentsResponse,
  KnowledgeBaseType,
} from '@/types/api'

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  const { data } = await apiClient.get<KnowledgeBase[]>('/knowledge-bases')
  return data
}

export async function getKnowledgeBaseTypes(): Promise<KnowledgeBaseType[]> {
  const { data } = await apiClient.get<{ types: KnowledgeBaseType[] }>('/knowledge-base-types')
  return data.types
}

export async function createKnowledgeBase(
  payload: CreateKnowledgeBaseRequest,
): Promise<KnowledgeBase> {
  const { data } = await apiClient.post<KnowledgeBase>('/knowledge-bases', payload)
  return data
}

export async function deleteKnowledgeBase(kbId: string): Promise<BuildResponse> {
  const { data } = await apiClient.delete<BuildResponse>(`/knowledge-bases/${kbId}`)
  return data
}

export async function buildKnowledgeBase(kbId: string): Promise<BuildResponse> {
  const { data } = await apiClient.post<BuildResponse>(`/knowledge-bases/${kbId}/build`)
  return data
}

export async function getKnowledgeBaseDocuments(
  kbId: string,
): Promise<KnowledgeBaseDocumentsResponse> {
  const { data } = await apiClient.get<KnowledgeBaseDocumentsResponse>(`/knowledge-bases/${kbId}/documents`)
  return data
}

export async function deleteKnowledgeBaseDocument(
  kbId: string,
  fileName: string,
): Promise<BuildResponse> {
  const { data } = await apiClient.delete<BuildResponse>(
    `/knowledge-bases/${kbId}/documents/${encodeURIComponent(fileName)}`,
  )
  return data
}

export async function uploadDocumentToKnowledgeBase(
  kbId: string,
  file: File,
): Promise<BuildResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<BuildResponse>(
    `/knowledge-bases/${kbId}/upload`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return data
}
