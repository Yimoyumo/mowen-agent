<script setup lang="ts">
import { ref, watch } from 'vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import ChatArea from '@/components/chat/ChatArea.vue'
import ContextPanel from '@/components/chat/ContextPanel.vue'
import { useConfig } from '@/composables/useConfig'
import { useChat } from '@/composables/useChat'
import { useKnowledgeBaseManager } from '@/composables/useKnowledgeBase'
import { useChatStore } from '@/stores/chat'

const { config, isReady } = useConfig()
const { question, loading, streaming, currentResult, sendQuestion, setQuestion, selectHistory } = useChat()
const kbManager = useKnowledgeBaseManager()
const chatStore = useChatStore()

const showContext = ref(false)
const chatAreaRef = ref<InstanceType<typeof ChatArea> | null>(null)
const sidebarCollapsed = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function backToHome() {
  chatStore.setCurrentResult(null)
}

function handleRemoveHistory(index: number) {
  chatStore.removeHistory(index)
}

function handleClearHistory() {
  chatStore.clearHistory()
}

watch(
  () => currentResult.value?.answer,
  () => {
    chatAreaRef.value?.scrollToBottom()
  },
  { flush: 'post' },
)
</script>

<template>
  <div class="home" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <AppSidebar
      :creating="kbManager.creating.value"
      :building="kbManager.building.value"
      :uploading="kbManager.uploading.value"
      :kb-types="kbManager.kbTypes.value"
      :collapsed="sidebarCollapsed"
      :chat-history="chatStore.history"
      :current-result="currentResult"
      @create-kb="(name, description, kbType) => kbManager.handleCreate({ name, description, kb_type: kbType })"
      @delete-kb="kbManager.handleDelete"
      @build-kb="kbManager.handleBuild"
      @upload-kb="kbManager.handleUpload"
      @select-kb="kbManager.selectKb"
      @toggle-collapse="toggleSidebar"
      @select-history="selectHistory"
      @remove-history="handleRemoveHistory"
      @clear-history="handleClearHistory"
    />

    <div class="main-wrapper">
      <ChatArea
        ref="chatAreaRef"
        v-model:question="question"
        :loading="loading"
        :streaming="streaming"
        :disabled="!isReady"
        :kb-selected="!!kbManager.store.currentKbId"
        :knowledge-bases="kbManager.store.knowledgeBases"
        :current-kb-id="kbManager.store.currentKbId"
        :current-result="currentResult"
        :config="config"
        @send="sendQuestion"
        @select-example="setQuestion"
        @select-kb="kbManager.selectKb"
        @toggle-context="showContext = true"
        @back-home="backToHome"
      />
    </div>

    <ContextPanel
      :contexts="currentResult?.contexts ?? []"
      :visible="showContext"
      @close="showContext = false"
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
  display: flex;
  flex-direction: column;
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
