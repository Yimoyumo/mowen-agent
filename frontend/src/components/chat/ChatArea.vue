<script setup lang="ts">
import { computed, ref, nextTick, watch } from 'vue'
import HomeHero from '@/components/home/HomeHero.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import type { ChatMessage as ChatMessageType, ConfigResponse } from '@/types/api'

  interface Props {
  question: string
  loading: boolean
  streaming: boolean
  disabled: boolean
  messages: ChatMessageType[]
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
  config: ConfigResponse | null
}

const props = withDefaults(defineProps<Props>(), {
  config: null,
})
const emit = defineEmits<{
  'update:question': [value: string]
  send: []
  stop: []
  selectExample: [question: string]
  selectKb: [kbId: string]
  toggleContext: []
  newConversation: []
}>()

const hasMessages = computed(() => props.messages.length > 0)
const messagesRef = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 监听消息变化，自动滚动
watch(() => props.messages.length, () => scrollToBottom())
watch(() => props.messages.map(m => m.content).join(''), () => scrollToBottom())

defineExpose({ scrollToBottom })
</script>

<template>
  <main class="chat-area">
    <div class="chat-topbar">
      <div class="topbar-left">
        <button v-if="hasMessages" class="topbar-btn" @click="emit('newConversation')">
          <el-icon><Plus /></el-icon>
          <span>新对话</span>
        </button>
      </div>
      <div class="topbar-right">
        <button
          v-if="hasMessages && messages.some(m => m.contexts && m.contexts.length > 0)"
          class="topbar-btn"
          @click="emit('toggleContext')"
        >
          <el-icon><Document /></el-icon>
          <span>参考上下文</span>
        </button>
        <el-popover v-if="config" placement="bottom-end" :width="320" trigger="click">
          <template #reference>
            <button class="topbar-btn">
              <el-icon><Setting /></el-icon>
              <span>配置</span>
            </button>
          </template>
          <div class="config-popover">
            <div class="config-popover-title">当前配置</div>
            <div class="config-popover-grid">
              <div class="config-popover-item">
                <span class="config-popover-label">对话厂商</span>
                <span class="config-popover-value">{{ config.chat_provider }}</span>
              </div>
              <div class="config-popover-item">
                <span class="config-popover-label">对话模型</span>
                <span class="config-popover-value">{{ config.chat_model }}</span>
              </div>
              <div class="config-popover-item">
                <span class="config-popover-label">Embedding</span>
                <span class="config-popover-value">{{ config.embedding_model }}</span>
              </div>
              <div class="config-popover-item">
                <span class="config-popover-label">top_k</span>
                <span class="config-popover-value">{{ config.top_k }}</span>
              </div>
              <div class="config-popover-item">
                <span class="config-popover-label">查询扩写</span>
                <el-tag :type="config.enable_query_expansion ? 'success' : 'info'" size="small">
                  {{ config.enable_query_expansion ? '开启' : '关闭' }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-popover>
      </div>
    </div>

    <div ref="messagesRef" class="chat-messages">
      <HomeHero v-if="!hasMessages" @select="emit('selectExample', $event)" />

      <template v-else>
        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :type="msg.role"
          :content="msg.content"
          :streaming="streaming && msg.id === messages[messages.length - 1].id"
          :contexts="msg.contexts"
          @toggle-context="emit('toggleContext')"
        />
      </template>
    </div>

    <ChatInput
      :model-value="question"
      :loading="loading"
      :disabled="disabled"
      :knowledge-bases="knowledgeBases"
      :current-kb-id="currentKbId"
      @update:model-value="emit('update:question', $event)"
      @send="emit('send')"
      @stop="emit('stop')"
      @select-kb="emit('selectKb', $event)"
    />
  </main>
</template>

<style scoped>
.chat-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}

.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.topbar-left,
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.topbar-btn {
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

.topbar-btn:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}

.config-popover-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.config-popover-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-popover-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 4px 0;
  border-bottom: 1px solid #f5f5f5;
}

.config-popover-item:last-child {
  border-bottom: none;
}

.config-popover-label {
  color: #909399;
}

.config-popover-value {
  color: #303133;
  font-weight: 500;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
