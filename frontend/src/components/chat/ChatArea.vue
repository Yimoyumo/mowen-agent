<script setup lang="ts">
import { computed, ref } from 'vue'
import HomeHero from '@/components/home/HomeHero.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import type { AskResponse, ConfigResponse } from '@/types/api'

interface Props {
  question: string
  loading: boolean
  streaming: boolean
  disabled: boolean
  kbSelected: boolean
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
  currentResult: AskResponse | null
  config: ConfigResponse | null
}

const props = withDefaults(defineProps<Props>(), {
  config: null,
})
const emit = defineEmits<{
  'update:question': [value: string]
  send: []
  selectExample: [question: string]
  selectKb: [kbId: string]
  toggleContext: []
  backHome: []
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
    <div class="chat-topbar">
      <button v-if="hasResult" class="back-home-btn" @click="emit('backHome')">
        <el-icon><Back /></el-icon>
        <span>返回首页</span>
      </button>
      <div v-else class="topbar-spacer" />
      <el-popover v-if="config" placement="bottom-end" :width="320" trigger="click">
        <template #reference>
          <button class="config-btn">
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
              <span class="config-popover-label">切分方式</span>
              <span class="config-popover-value">
                {{ config.chapter_split ? '按章节切分' : '普通切分' }}
              </span>
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

.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.topbar-spacer {
  flex: 1;
}

.config-btn {
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

.config-btn:hover {
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

.back-home-btn {
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

.back-home-btn:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
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
