<script setup lang="ts">
import { computed, ref } from 'vue'
import HomeHero from '@/components/home/HomeHero.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import type { AskResponse } from '@/types/api'

interface Props {
  question: string
  loading: boolean
  streaming: boolean
  disabled: boolean
  kbSelected: boolean
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
  currentResult: AskResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:question': [value: string]
  send: []
  selectExample: [question: string]
  selectKb: [kbId: string]
  toggleContext: []
}>()

const hasResult = computed(() => props.currentResult !== null)
const messagesRef = ref<HTMLElement | null>(null)

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

defineExpose({ scrollToBottom })
</script>

<template>
  <main class="chat-area">
    <div ref="messagesRef" class="chat-messages">
      <HomeHero v-if="!hasResult" :kb-selected="kbSelected" @select="emit('selectExample', $event)" />

      <template v-else>
        <ChatMessage
          type="user"
          title="用户问题"
          :content="currentResult!.question"
        />
        <ChatMessage
          type="ai"
          title="模型回答"
          :content="currentResult!.answer"
          :streaming="streaming"
        />
      </template>
    </div>

    <div class="chat-footer">
      <ChatInput
        :model-value="question"
        :loading="loading"
        :disabled="disabled"
        :kb-selected="kbSelected"
        :knowledge-bases="knowledgeBases"
        :current-kb-id="currentKbId"
        @update:model-value="emit('update:question', $event)"
        @send="emit('send')"
        @select-kb="emit('selectKb', $event)"
      />
      <button
        v-if="hasResult && currentResult!.contexts.length > 0"
        class="context-toggle"
        @click="emit('toggleContext')"
      >
        <el-icon><Document /></el-icon>
        <span>查看参考上下文 ({{ currentResult!.contexts.length }})</span>
      </button>
    </div>
  </main>
</template>

<style scoped>
.chat-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.chat-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
}

.context-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.context-toggle:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}
</style>
