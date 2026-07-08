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
  streamEnabled: boolean
  showReasoning: boolean
  modelOptions?: string[]
  activeModel?: string
  modelVisionMap?: Record<string, boolean>
  tokenStats?: { input_tokens: number; output_tokens: number; context_window: number } | null
}

const props = withDefaults(defineProps<Props>(), {
  config: null,
  modelOptions: () => [],
  activeModel: '',
  modelVisionMap: () => ({}),
  tokenStats: null,
})
const emit = defineEmits<{
  'update:question': [value: string]
  'update:streamEnabled': [value: boolean]
  'update:showReasoning': [value: boolean]
  'update:thinking': [value: boolean]
  'update:reasoningEffort': [value: string]
  send: [uploadedFiles: { token: string; filename: string }[]]
  stop: []
  selectExample: [question: string]
  selectKb: [kbId: string]
  selectModel: [modelRef: string]
  toggleContext: []
  newConversation: []
}>()

const hasMessages = computed(() => props.messages.length > 0)
const messagesRef = ref<HTMLElement | null>(null)

// Token 用量展示
const tokenUsageColor = computed(() => {
  if (!props.tokenStats || props.tokenStats.context_window <= 0) return '#409eff'
  const ratio = (props.tokenStats.input_tokens + props.tokenStats.output_tokens) / props.tokenStats.context_window
  if (ratio > 0.9) return '#f56c6c'
  if (ratio > 0.7) return '#e6a23c'
  return '#67c23a'
})

function fmtTokens(n: number): string {
  if (n <= 0) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1000) return `${Math.round(n / 1024)}K`
  return String(n)
}

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
        <!-- Token 用量提示 -->
        <div v-if="tokenStats" class="token-usage" :title="`输入 ${tokenStats.input_tokens} + 输出 ${tokenStats.output_tokens} = ${tokenStats.input_tokens + tokenStats.output_tokens} tokens`">
          <template v-if="tokenStats.context_window > 0">
            <span class="token-usage-label">上下文</span>
            <el-progress
              :percentage="Math.min(100, Math.round((tokenStats.input_tokens + tokenStats.output_tokens) / tokenStats.context_window * 100))"
              :stroke-width="6"
              :show-text="false"
              :color="tokenUsageColor"
              style="width: 60px"
            />
            <span class="token-usage-text">{{ fmtTokens(tokenStats.input_tokens + tokenStats.output_tokens) }} / {{ fmtTokens(tokenStats.context_window) }}</span>
          </template>
          <template v-else>
            <span class="token-usage-text">{{ fmtTokens(tokenStats.input_tokens + tokenStats.output_tokens) }} tokens</span>
          </template>
        </div>
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
            <div class="config-popover-switches">
              <div class="config-popover-switch-item">
                <span class="config-popover-label">思考模式</span>
                <el-switch
                  :model-value="config.thinking"
                  size="small"
                  @update:model-value="emit('update:thinking', $event as boolean)"
                />
              </div>
              <div class="config-popover-switch-item" v-if="config.thinking">
                <span class="config-popover-label">推理强度</span>
                <el-select
                  :model-value="config.reasoning_effort || 'medium'"
                  size="small"
                  style="width: 100px"
                  @change="(v: string) => emit('update:reasoningEffort', v)"
                >
                  <el-option label="低" value="low" />
                  <el-option label="中" value="medium" />
                  <el-option label="高" value="high" />
                </el-select>
              </div>
            </div>

            <!-- 运行时开关 -->
            <div class="config-popover-divider"></div>
            <div class="config-popover-switches">
              <div class="config-popover-switch-item">
                <span class="config-popover-label">流式输出</span>
                <el-switch
                  :model-value="streamEnabled"
                  size="small"
                  @update:model-value="emit('update:streamEnabled', $event as boolean)"
                />
              </div>
              <div class="config-popover-switch-item">
                <span class="config-popover-label">显示推理过程</span>
                <el-switch
                  :model-value="showReasoning"
                  size="small"
                  @update:model-value="emit('update:showReasoning', $event as boolean)"
                />
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
          :streaming="streaming && msg.id === messages.at(-1)?.id"
          :contexts="msg.contexts"
          :reasoning="msg.reasoning"
          :segments="msg.segments"
          :files="msg.files"
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
      :model-options="modelOptions"
      :active-model="activeModel"
      :model-vision-map="modelVisionMap"
      @update:model-value="emit('update:question', $event)"
      @send="(files: any) => emit('send', files)"
      @stop="emit('stop')"
      @select-kb="emit('selectKb', $event)"
      @select-model="emit('selectModel', $event)"
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

.token-usage {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f5f7fa;
}

.token-usage-label {
  color: #909399;
}

.token-usage-text {
  color: #606266;
  font-variant-numeric: tabular-nums;
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

.config-popover-divider {
  height: 1px;
  background: #f0f0f0;
  margin: 8px 0;
}

.config-popover-switches {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-popover-switch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
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
