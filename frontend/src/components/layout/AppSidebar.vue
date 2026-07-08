<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import type { Conversation } from '@/types/api'
import KnowledgeBasePanel from './KnowledgeBasePanel.vue'
import ChatHistoryPanel from './ChatHistoryPanel.vue'
import { getExtensions, testMcpServers, type ExtensionsInfo, type McpTestResult } from '@/api/settingsApi'

interface Props {
  creating: boolean
  building: boolean
  uploading: boolean
  kbTypes: { value: string; label: string }[]
  collapsed: boolean
  conversations: Conversation[]
  currentConversationId: string | null
}

defineProps<Props>()
const emit = defineEmits<{
  'create-kb': [name: string, description: string, kbType: string]
  'delete-kb': [kbId: string]
  'build-kb': [kbId: string]
  'upload-kb': [kbId: string, file: File]
  'select-kb': [kbId: string]
  'toggle-collapse': []
  'select-conversation': [id: string]
  'remove-conversation': [id: string]
  'clear-conversations': []
  'new-conversation': []
}>()

const router = useRouter()
const extensions = ref<ExtensionsInfo | null>(null)
const mcpStatus = ref<Record<string, McpTestResult>>({})
const testingMcp = ref(false)

function handleCreate(name: string, description: string, kbType: string) {
  emit('create-kb', name, description, kbType)
}

function goSettings() {
  router.push('/settings')
}

function goScheduledTasks() {
  router.push('/scheduled-tasks')
}

async function loadExtensions() {
  try {
    extensions.value = await getExtensions()
    // 加载完配置后立即测试连接状态
    await testMcpStatus()
  } catch {
    // 静默
  }
}

async function testMcpStatus() {
  testingMcp.value = true
  try {
    mcpStatus.value = await testMcpServers()
  } catch {
    // 静默
  } finally {
    testingMcp.value = false
  }
}

onMounted(loadExtensions)
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
          :conversations="conversations"
          :current-id="currentConversationId"
          @select="emit('select-conversation', $event)"
          @remove="emit('remove-conversation', $event)"
          @clear="emit('clear-conversations')"
          @new-conversation="emit('new-conversation')"
        />
      </el-card>
    </div>

    <div v-if="!collapsed && extensions && extensions.mcp_servers.length > 0" class="extensions-info">
      <div class="ext-group">
        <div class="ext-title">
          <el-icon><Connection /></el-icon>
          <span>MCP 服务器 ({{ extensions.mcp_servers.length }})</span>
          <button class="ext-refresh" :disabled="testingMcp" @click="testMcpStatus" title="测试连接">
            <el-icon :class="{ spinning: testingMcp }"><Refresh /></el-icon>
          </button>
        </div>
        <div v-for="mcp in extensions.mcp_servers" :key="mcp.name" class="ext-item" :title="mcpStatus[mcp.name]?.error || `${mcp.command} ${mcp.args.join(' ')}`">
          <span
            class="ext-dot"
            :class="{
              active: mcpStatus[mcp.name]?.ok === true,
              inactive: mcpStatus[mcp.name]?.ok === false,
              pending: mcpStatus[mcp.name] === undefined && !testingMcp
            }"
          ></span>
          <span class="ext-name">{{ mcp.name }}</span>
          <span class="ext-tag" v-if="mcpStatus[mcp.name]?.ok">{{ mcpStatus[mcp.name]?.tool_count ?? 0 }} 工具</span>
          <span class="ext-tag err" v-else-if="mcpStatus[mcp.name]?.ok === false">不可用</span>
          <span class="ext-tag" v-else>{{ mcp.transport }}</span>
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      <button class="settings-btn" :title="collapsed ? '定时任务' : ''" @click="goScheduledTasks">
        <el-icon><AlarmClock /></el-icon>
        <span v-if="!collapsed">定时任务</span>
      </button>
      <button class="settings-btn" :title="collapsed ? '设置' : ''" @click="goSettings">
        <el-icon><Setting /></el-icon>
        <span v-if="!collapsed">设置</span>
      </button>
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

.extensions-info {
  padding: 8px 4px 12px;
  margin-bottom: 8px;
  border-top: 1px solid #f0f0f0;
  max-height: 200px;
  overflow-y: auto;
  flex-shrink: 0;
}

.ext-group {
  margin-bottom: 8px;
}

.ext-group:last-child {
  margin-bottom: 0;
}

.ext-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ext-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}

.ext-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ext-dot.active {
  background: #67c23a;
}

.ext-dot.inactive {
  background: #f56c6c;
}

.ext-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ext-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #f0f0f0;
  color: #909399;
}

.ext-warn {
  color: #e6a23c;
  font-size: 12px;
}

.ext-dot.pending {
  background: #c0c4cc;
}

.ext-tag.err {
  background: #fef0f0;
  color: #f56c6c;
}

.ext-refresh {
  border: none;
  background: none;
  cursor: pointer;
  padding: 0;
  margin-left: auto;
  color: #909399;
  display: flex;
  align-items: center;
}

.ext-refresh:hover {
  color: #409eff;
}

.ext-refresh:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.ext-refresh .spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.sidebar-footer {
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #606266;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.app-sidebar.collapsed .settings-btn {
  justify-content: center;
  padding: 8px;
}

.settings-btn:hover {
  background: #f5f5f5;
  color: #1d1d1d;
}
</style>
