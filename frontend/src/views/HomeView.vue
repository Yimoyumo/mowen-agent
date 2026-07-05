<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import ChatArea from '@/components/chat/ChatArea.vue'
import ContextPanel from '@/components/chat/ContextPanel.vue'
import { useConfig } from '@/composables/useConfig'
import { useChat } from '@/composables/useChat'
import { useKnowledgeBaseManager } from '@/composables/useKnowledgeBase'
import { useChatStore } from '@/stores/chat'

const { config, isReady } = useConfig()
const {
  question,
  loading,
  streaming,
  streamEnabled,
  showReasoning,
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
        @send="(files: any) => sendMessage(undefined, files)"
        @stop="stopStreaming"
        @select-example="setQuestion"
        @select-kb="kbManager.selectKb"
        @toggle-context="toggleContext"
        @new-conversation="createNewConversation"
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
