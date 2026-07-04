<script setup lang="ts">
import { computed } from 'vue'
import type { ConfigResponse, AskResponse } from '@/types/api'
import KnowledgeBasePanel from './KnowledgeBasePanel.vue'
import ChatHistoryPanel from './ChatHistoryPanel.vue'

interface Props {
  config: ConfigResponse | null
  creating: boolean
  building: boolean
  uploading: boolean
  kbTypes: { value: string; label: string }[]
  collapsed: boolean
  chatHistory: AskResponse[]
  currentResult: AskResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'create-kb': [name: string, description: string, kbType: string]
  'delete-kb': [kbId: string]
  'build-kb': [kbId: string]
  'upload-kb': [kbId: string, file: File]
  'select-kb': [kbId: string]
  'toggle-collapse': []
  'select-history': [item: AskResponse]
  'remove-history': [index: number]
  'clear-history': []
}>()

const splitLabel = computed(() =>
  props.config?.chapter_split ? '章节阈值' : 'chunk_size',
)

const splitValue = computed(() =>
  props.config?.chapter_split
    ? `${props.config.chapter_chunk_threshold} 字`
    : `${props.config?.chunk_size} 字`,
)

function handleCreate(name: string, description: string, kbType: string) {
  emit('create-kb', name, description, kbType)
}
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="logo" :class="{ collapsed }">
        <span class="logo-icon">
          <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="40" height="40" rx="10" fill="#1d1d1d"/>
            <path d="M12 28V12h4l8 10V12h4v16h-4l-8-10v10h-4z" fill="#fff"/>
          </svg>
        </span>
        <span v-if="!collapsed" class="logo-text">墨问</span>
      </div>
      <button class="collapse-btn" :title="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="emit('toggle-collapse')">
        <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
      </button>
    </div>

    <div v-if="!collapsed" class="sidebar-body">
      <el-card v-if="config" class="config-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Setting /></el-icon>
            <span>当前配置</span>
          </div>
        </template>
        <div class="config-grid">
          <div class="config-item">
            <span class="config-label">对话厂商</span>
            <span class="config-value">{{ config.chat_provider }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">对话模型</span>
            <span class="config-value">{{ config.chat_model }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">Embedding</span>
            <span class="config-value">{{ config.embedding_model }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">top_k</span>
            <span class="config-value">{{ config.top_k }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">切分方式</span>
            <span class="config-value">
              {{ config.chapter_split ? '按章节切分' : '普通切分' }}
            </span>
          </div>
          <div class="config-item">
            <span class="config-label">{{ splitLabel }}</span>
            <span class="config-value">{{ splitValue }}</span>
          </div>
          <div class="config-item full-width">
            <span class="config-label">查询扩写</span>
            <span class="config-value">
              <el-tag :type="config.enable_query_expansion ? 'success' : 'info'" size="small">
                {{ config.enable_query_expansion ? '开启' : '关闭' }}
              </el-tag>
            </span>
          </div>
        </div>
      </el-card>

      <el-card class="action-card" shadow="never">
        <KnowledgeBasePanel
          :creating="creating"
          :building="building"
          :uploading="uploading"
          :kb-types="kbTypes"
          @create="handleCreate"
          @delete="emit('delete-kb', $event)"
          @build="emit('build-kb', $event)"
          @upload="(kbId: string, file: File) => emit('upload-kb', kbId, file)"
          @select="emit('select-kb', $event)"
        />
      </el-card>

      <el-card class="action-card" shadow="never">
        <ChatHistoryPanel
          :history="chatHistory"
          :current="currentResult"
          @select="emit('select-history', $event)"
          @remove="emit('remove-history', $event)"
          @clear="emit('clear-history')"
        />
      </el-card>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 300px;
  min-width: 300px;
  height: 100vh;
  background: #fafafa;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  padding: 16px;
  transition: width 0.3s ease, min-width 0.3s ease, padding 0.3s ease;
}

.app-sidebar.collapsed {
  width: 64px;
  min-width: 64px;
  padding: 16px 8px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.app-sidebar.collapsed .sidebar-header {
  flex-direction: column;
  gap: 12px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px;
}

.logo.collapsed {
  justify-content: center;
}

.logo-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-icon svg {
  width: 100%;
  height: 100%;
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: #1d1d1d;
  white-space: nowrap;
}

.collapse-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: #f5f5f5;
  border-color: #1d1d1d;
  color: #1d1d1d;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-card,
.action-card {
  border: none;
  background: #fff;
  border-radius: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.config-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px solid #f5f5f5;
}

.config-item:last-child {
  border-bottom: none;
}

.config-label {
  color: #909399;
}

.config-value {
  color: #303133;
  font-weight: 500;
  text-align: right;
  max-width: 140px;
  word-break: break-all;
}
</style>
