<script setup lang="ts">
import type { AskResponse } from '@/types/api'
import KnowledgeBasePanel from './KnowledgeBasePanel.vue'
import ChatHistoryPanel from './ChatHistoryPanel.vue'

interface Props {
  creating: boolean
  building: boolean
  uploading: boolean
  kbTypes: { value: string; label: string }[]
  collapsed: boolean
  chatHistory: AskResponse[]
  currentResult: AskResponse | null
}

defineProps<Props>()
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
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-card {
  border: none;
  background: #fff;
  border-radius: 12px;
  height: 50%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.action-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
