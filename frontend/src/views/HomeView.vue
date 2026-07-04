<script setup lang="ts">
import { ref, watch } from 'vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppHistory from '@/components/layout/AppHistory.vue'
import ChatArea from '@/components/chat/ChatArea.vue'
import ContextPanel from '@/components/chat/ContextPanel.vue'
import { useConfig } from '@/composables/useConfig'
import { useChat } from '@/composables/useChat'
import { useKnowledgeBaseManager } from '@/composables/useKnowledgeBase'

const { config, isReady } = useConfig()
const { question, loading, streaming, currentResult, history, sendQuestion, selectHistory, setQuestion } = useChat()
const kbManager = useKnowledgeBaseManager()

const showContext = ref(false)
const chatAreaRef = ref<InstanceType<typeof ChatArea> | null>(null)

watch(
  () => currentResult.value?.answer,
  () => {
    chatAreaRef.value?.scrollToBottom()
  },
  { flush: 'post' },
)
</script>

<template>
  <div class="home">
    <AppSidebar
      :config="config"
      :creating="kbManager.creating.value"
      :building="kbManager.building.value"
      :uploading="kbManager.uploading.value"
      :kb-types="kbManager.kbTypes.value"
      @create-kb="(name, description, kbType) => kbManager.handleCreate({ name, description, kb_type: kbType })"
      @delete-kb="kbManager.handleDelete"
      @build-kb="kbManager.handleBuild"
      @upload-kb="kbManager.handleUpload"
      @select-kb="kbManager.selectKb"
    />

    <div class="main-wrapper">
      <AppHistory
        v-if="history.length > 0"
        :history="history"
        :current="currentResult"
        @select="selectHistory"
      />

      <ChatArea
        ref="chatAreaRef"
        v-model:question="question"
        :loading="loading"
        :streaming="streaming"
        :disabled="!isReady"
        :current-result="currentResult"
        @send="sendQuestion"
        @select-example="setQuestion"
        @toggle-context="showContext = true"
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
