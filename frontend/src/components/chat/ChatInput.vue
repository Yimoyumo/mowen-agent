<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue: string
  loading: boolean
  disabled: boolean
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  stop: []
  selectKb: [kbId: string]
}>()

const hasContent = computed(() => props.modelValue.trim().length > 0)
const canSend = computed(() => hasContent.value && !props.loading && !props.disabled)

function handleInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && canSend.value) {
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
        placeholder="输入你的问题…"
        :disabled="disabled"
        @input="handleInput"
        @keydown="handleKeydown"
      />
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <el-select
            v-if="knowledgeBases.length > 0"
            :model-value="currentKbId"
            placeholder="知识库（可选）"
            size="small"
            class="kb-select"
            clearable
            @change="(val: string) => emit('selectKb', val || '')"
          >
            <template #prefix>
              <el-icon><Collection /></el-icon>
            </template>
            <el-option
              v-for="kb in knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
          <span v-if="currentKbId" class="rag-badge">RAG 已启用</span>
        </div>
        <button
          v-if="loading"
          class="stop-btn"
          @click="emit('stop')"
        >
          <el-icon><VideoPause /></el-icon>
          <span>停止</span>
        </button>
        <button
          v-else
          class="send-btn"
          :class="{ active: canSend }"
          :disabled="!canSend"
          @click="emit('send')"
        >
          <el-icon v-if="false" class="is-loading"><Loading /></el-icon>
          <span v-else class="send-text">发送</span>
        </button>
      </div>
    </div>
    <div class="input-footer">
      <span class="input-tip">Enter 发送 · Shift + Enter 换行{{ currentKbId ? ' · RAG 增强' : '' }}</span>
    </div>
  </div>
</template>

<style scoped>
.chat-input-wrapper {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 12px 24px 16px;
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
  align-items: center;
}

.kb-select {
  width: 180px;
}

.kb-select :deep(.el-input__wrapper) {
  border-radius: 999px;
  box-shadow: 0 0 0 1px #e4e7ed inset;
}

.rag-badge {
  font-size: 11px;
  color: #52c41a;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
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

.send-text {
  padding: 0 4px;
}

.stop-btn {
  min-width: 64px;
  height: 36px;
  border-radius: 18px;
  border: none;
  background: #1d1d1d;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
  font-weight: 500;
}

.stop-btn:hover {
  background: #000;
  opacity: 0.85;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 800px;
  margin: 8px auto 0;
  padding: 0 4px;
}

.input-tip {
  font-size: 11px;
  color: #c0c4cc;
}
</style>
