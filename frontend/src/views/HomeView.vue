<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import ChatArea from '@/components/chat/ChatArea.vue'
import ContextPanel from '@/components/chat/ContextPanel.vue'
import { useConfig } from '@/composables/useConfig'
import { useChat } from '@/composables/useChat'
import { useKnowledgeBaseManager } from '@/composables/useKnowledgeBase'
import { useChatStore } from '@/stores/chat'
import { useSettings } from '@/composables/useSettings'
import { updateSettings } from '@/api/settingsApi'
import { getConfig } from '@/api/configApi'
import { apiClient } from '@/api'
import { ElMessage } from 'element-plus'

const { config, isReady } = useConfig()
const { settings: us, providers, handleSelectModel } = useSettings()
const {
  question,
  loading,
  streaming,
  streamEnabled,
  showReasoning,
  tokenStats,
  messages,
  currentConversation,
  conversations,
  sendMessage,
  stopStreaming,
  selectConversation,
  deleteConversation,
  createNewConversation,
  clearAllConversations,
  setQuestion,
} = useChat()
const kbManager = useKnowledgeBaseManager()
const chatStore = useChatStore()

const sidebarCollapsed = ref(false)
const showContext = ref(false)

// 获取有上下文的消息
const contextMessages = computed(() =>
  messages.value.filter(m => m.contexts && m.contexts.length > 0),
)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function toggleContext() {
  showContext.value = !showContext.value
}

function handleRemoveConversation(id: string) {
  deleteConversation(id)
}

function handleClearConversations() {
  clearAllConversations()
}

// 只收集有 API Key 的厂商的模型
const modelOptions = computed(() => {
  if (!providers.value) return []
  const opts: string[] = []
  for (const p of providers.value.providers) {
    if (!p.has_api_key) continue
    for (const m of p.models) {
      opts.push(`${p.id}/${m}`)
    }
  }
  return opts
})

const activeModel = computed(() => providers.value?.active_model || '')

// 模型视觉能力映射
const modelVisionMap = ref<Record<string, boolean>>({})

watch(providers, async (p) => {
  if (!p) return
  try {
    const res = await apiClient.get('/settings/model-vision')
    modelVisionMap.value = res.data
  } catch {
    // 获取失败静默忽略
  }
}, { immediate: true })

function handleSwitchModel(ref: string) {
  handleSelectModel(ref)
}

// 更新思考模式 / 推理强度 → 保存到 settings 并刷新 config
async function handleUpdateThinking(val: boolean) {
  if (config.value) config.value.thinking = val
  try {
    await updateSettings({ generation: { thinking: val } })
    config.value = await getConfig()
  } catch {
    ElMessage.error('保存失败')
  }
}

async function handleUpdateReasoningEffort(val: string) {
  if (config.value) config.value.reasoning_effort = val
  try {
    await updateSettings({ generation: { reasoning_effort: val } })
    config.value = await getConfig()
  } catch {
    ElMessage.error('保存失败')
  }
}

// 应用启动时：从后端同步对话历史
onMounted(() => {
  chatStore.syncFromBackend()
})
</script>

<template>
  <div class="home" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <AppSidebar
      :creating="kbManager.creating.value"
      :building="kbManager.building.value"
      :uploading="kbManager.uploading.value"
      :kb-types="kbManager.kbTypes.value"
      :collapsed="sidebarCollapsed"
      :conversations="conversations"
      :current-conversation-id="chatStore.currentId"
      @create-kb="(name, description, kbType) => kbManager.handleCreate({ name, description, kb_type: kbType })"
      @delete-kb="kbManager.handleDelete"
      @build-kb="kbManager.handleBuild"
      @upload-kb="kbManager.handleUpload"
      @select-kb="kbManager.selectKb"
      @toggle-collapse="toggleSidebar"
      @select-conversation="selectConversation"
      @remove-conversation="handleRemoveConversation"
      @clear-conversations="handleClearConversations"
      @new-conversation="createNewConversation"
    />

    <div class="main-wrapper" :class="{ 'context-open': showContext }">
      <ChatArea
        v-model:question="question"
        v-model:stream-enabled="streamEnabled"
        v-model:show-reasoning="showReasoning"
        :loading="loading"
        :streaming="streaming"
        :disabled="!isReady"
        :messages="messages"
        :knowledge-bases="kbManager.store.knowledgeBases"
        :current-kb-id="kbManager.store.currentKbId"
        :config="config"
        :model-options="modelOptions"
        :active-model="activeModel"
        :model-vision-map="modelVisionMap"
        :token-stats="tokenStats"
        @send="(files: any) => sendMessage(undefined, files)"
        @stop="stopStreaming"
        @select-example="setQuestion"
        @select-kb="kbManager.selectKb"
        @toggle-context="toggleContext"
        @new-conversation="createNewConversation"
        @select-model="handleSwitchModel"
        @update:thinking="handleUpdateThinking"
        @update:reasoning-effort="handleUpdateReasoningEffort"
      />
    </div>

    <ContextPanel
      :contexts="contextMessages.flatMap(m => m.contexts ?? [])"
      :visible="showContext"
      @close="toggleContext"
    />
  </div>
</template>

<style scoped>
.home {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #fff;
  transition: padding 0.3s ease;
}

.main-wrapper {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 1024px) {
  .home {
    flex-direction: column;
  }

  .main-wrapper {
    height: 100%;
  }
}
</style>
