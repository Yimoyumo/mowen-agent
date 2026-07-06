<script setup lang="ts">
import { ref } from 'vue'
import { useSettings } from '@/composables/useSettings'
import ModelSettings from '@/components/settings/ModelSettings.vue'
import RetrievalSettings from '@/components/settings/RetrievalSettings.vue'
import PersonaSettings from '@/components/settings/PersonaSettings.vue'
import MemorySettings from '@/components/settings/MemorySettings.vue'
import ProfileSettings from '@/components/settings/ProfileSettings.vue'
import { useRouter } from 'vue-router'

const {
  settings,
  providers,
  profile,
  memories,
  loading,
  saving,
  fetching,
  saveSettings,
  handleSaveProviderKey,
  handleFetchModels,
  handleSelectModel,
  handleAddProvider,
  handleDeleteProvider,
  saveProfile,
  handleAddMemory,
  handleUpdateMemory,
  handleDeleteMemory,
  handleClearMemories,
  handleReset,
} = useSettings()

const router = useRouter()
const activeTab = ref('model')

function goBack() {
  router.push('/')
}

// 适配 callback 模式的包装函数
function handleAddMem(type: string, content: string, callback: (ok: boolean) => void) {
  handleAddMemory(type, content).then(callback)
}

function handleUpdateMem(id: string, type: string, content: string, callback: (ok: boolean) => void) {
  handleUpdateMemory(id, type, content).then(callback)
}

function doFetchModels(providerId: string, callback: (models: string[]) => void) {
  handleFetchModels(providerId).then(callback)
}

function doAddProvider(name: string, baseUrl: string, apiKey: string, callback: (ok: boolean) => void) {
  handleAddProvider(name, baseUrl, apiKey).then(callback)
}
</script>

<template>
  <div class="settings-page">
    <header class="settings-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>返回</span>
        </button>
        <h1 class="settings-title">设置</h1>
      </div>
      <el-button text type="danger" @click="handleReset">
        <el-icon><RefreshLeft /></el-icon>
        重置全部
      </el-button>
    </header>

    <div v-loading="loading" class="settings-body">
      <el-tabs v-model="activeTab" tab-position="left" class="settings-tabs">
        <el-tab-pane label="模型设置" name="model">
          <ModelSettings
            v-if="settings && providers"
            :providers="providers"
            :fetching="fetching"
            :saving="saving"
            @save-key="handleSaveProviderKey"
            @fetch-models="doFetchModels"
            @add-provider="doAddProvider"
            @delete-provider="handleDeleteProvider"
          />
        </el-tab-pane>

        <el-tab-pane label="检索参数" name="retrieval">
          <RetrievalSettings
            v-if="settings"
            :settings="settings"
            :saving="saving"
            @save="saveSettings"
          />
        </el-tab-pane>

        <el-tab-pane label="人格设定" name="persona">
          <PersonaSettings
            v-if="settings"
            :settings="settings"
            :saving="saving"
            @save="saveSettings"
          />
        </el-tab-pane>

        <el-tab-pane label="模型记忆" name="memory">
          <MemorySettings
            :memories="memories"
            @add="handleAddMem"
            @update="handleUpdateMem"
            @delete="handleDeleteMemory"
            @clear="handleClearMemories"
          />
        </el-tab-pane>

        <el-tab-pane label="用户画像" name="profile">
          <ProfileSettings
            v-if="profile"
            :profile="profile"
            :saving="saving"
            @save="saveProfile"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
  overflow: hidden;
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
}

.settings-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.settings-body {
  flex: 1;
  overflow: hidden;
  padding: 24px;
}

.settings-tabs {
  height: 100%;
}

.settings-tabs :deep(.el-tabs__content) {
  height: 100%;
  overflow-y: auto;
}

.settings-tabs :deep(.el-tab-pane) {
  max-width: 720px;
  padding: 0 24px 48px;
}
</style>
