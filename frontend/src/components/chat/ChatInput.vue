<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue: string
  loading: boolean
  disabled: boolean
  kbSelected: boolean
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
}

const props = defineProps<Props>()
const isDisabled = computed(() => props.disabled || !props.kbSelected)
const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  selectKb: [kbId: string]
}>()

const hasContent = computed(() => props.modelValue.trim().length > 0)

function handleInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && hasContent.value && !isDisabled.value) {
    e.preventDefault()
    emit('send')
  }
}
</script>

<template>
  <div class="chat-input-wrapper">
    <div class="chat-input-box">
      <textarea
        :value="modelValue"
        rows="2"
        class="chat-textarea"
        :placeholder="kbSelected ? '输入你的问题…' : '请先选择一个知识库后再提问'"
        :disabled="isDisabled"
        @input="handleInput"
        @keydown="handleKeydown"
      />
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <button class="toolbar-btn" title="附件" :disabled="isDisabled">
            <el-icon><DocumentAdd /></el-icon>
          </button>
        </div>
        <button
          class="send-btn"
          :class="{ active: hasContent && !loading && !isDisabled, loading: loading }"
          :disabled="!hasContent || loading || isDisabled"
          @click="emit('send')"
        >
          <el-icon v-if="loading" class="is-loading"><Loading /></el-icon>
          <span v-else class="send-text">发送</span>
        </button>
      </div>
    </div>
    <div v-if="knowledgeBases.length > 0" class="kb-selector">
      <span class="kb-selector-label">知识库</span>
      <div class="kb-selector-list">
        <button
          v-for="kb in knowledgeBases"
          :key="kb.id"
          class="kb-selector-item"
          :class="{ active: kb.id === currentKbId }"
          :title="kb.name"
          @click="emit('selectKb', kb.id)"
        >
          {{ kb.name }}
        </button>
      </div>
    </div>
    <p class="input-tip">按 Enter 发送，Shift + Enter 换行</p>
  </div>
</template>

<style scoped>
.chat-input-wrapper {
  width: 100%;
  max-width: 800px;
  padding: 16px 0 8px;
  background: #fff;
}

.chat-input-box {
  max-width: 800px;
  margin: 0 auto;
  border: 1px solid #e4e7ed;
  border-radius: 16px;
  padding: 12px 16px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.chat-input-box:focus-within {
  border-color: #000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.chat-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  line-height: 1.6;
  color: #1d1d1d;
  background: transparent;
  font-family: inherit;
}

.chat-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.toolbar-left {
  display: flex;
  gap: 8px;
}

.toolbar-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: #f5f5f5;
  color: #606266;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  background: #e4e7ed;
}

.send-btn {
  min-width: 64px;
  height: 36px;
  border-radius: 18px;
  border: none;
  background: #e4e7ed;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: not-allowed;
  transition: all 0.2s;
  font-size: 14px;
  font-weight: 500;
}

.send-btn.active {
  background: #1d1d1d;
  cursor: pointer;
}

.send-btn.active:hover {
  background: #000;
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
}

.send-btn.loading {
  background: #1d1d1d;
  cursor: wait;
}

.send-text {
  padding: 0 4px;
}

.input-tip {
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
  margin: 8px 0 0;
}

.kb-selector {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 0 4px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}

.kb-selector-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  flex-shrink: 0;
}

.kb-selector-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  overflow-x: auto;
  scrollbar-width: none;
}

.kb-selector-list::-webkit-scrollbar {
  display: none;
}

.kb-selector-item {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kb-selector-item:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}

.kb-selector-item.active {
  background: #1d1d1d;
  border-color: #1d1d1d;
  color: #fff;
}
</style>
