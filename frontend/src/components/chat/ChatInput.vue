<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient } from '@/api/config'

const MAX_CHARS = 8000   // 单条消息最大字符数，超过自动转文件

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
  send: [uploadedFiles: { token: string; filename: string }[]]
  stop: []
  selectKb: [kbId: string]
}>()

const charCount = computed(() => props.modelValue.length)
const isOverLimit = computed(() => charCount.value > MAX_CHARS)
const hasContent = computed(() => props.modelValue.trim().length > 0)
const canSend = computed(() => hasContent.value && !props.loading && !props.disabled)

// 文件上传
const uploadedFiles = ref<{ token: string; filename: string; size: number }[]>([])
const uploading = ref(false)

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files) return

  uploading.value = true
  for (const file of files) {
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post('/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      uploadedFiles.value.push(res.data)
    } catch {
      // ignore upload errors silently
    }
  }
  uploading.value = false
  input.value = ''  // reset so same file can be re-uploaded
}

function removeFile(index: number) {
  uploadedFiles.value.splice(index, 1)
}

function handleInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && canSend.value) {
    e.preventDefault()
    doSend()
  }
}

async function uploadTextAsFile(text: string): Promise<{ token: string; filename: string } | null> {
  const blob = new Blob([text], { type: 'text/plain' })
  // generate a meaningful filename from first few words
  const firstLine = text.trim().split(/\n/)[0].slice(0, 40).replace(/[^\w\u4e00-\u9fff]/g, '_')
  const filename = `message_${firstLine || 'long_text'}.txt`
  const file = new File([blob], filename, { type: 'text/plain' })
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await apiClient.post('/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  } catch {
    ElMessage.error('文本文件上传失败')
    return null
  }
}

async function doSend() {
  const files = [...uploadedFiles.value]
  uploadedFiles.value = []
  const text = props.modelValue

  if (text.length > MAX_CHARS) {
    // 超长消息：截取摘要作为普通消息 + 完整内容转文件上传
    const summary = text.slice(0, 200).trim() + '…（完整内容已转为附件文件）'
    const uploaded = await uploadTextAsFile(text)
    if (uploaded) {
      files.push(uploaded)
    }
    emit('update:modelValue', summary)
    // 先清空输入框
    emit('send', files)
    // 恢复原始内容以便用户编辑（send 会清空 question，这里是异步的不好处理，
    // 我们主动清空 modelValue）
    emit('update:modelValue', '')
  } else {
    emit('send', files)
  }
}
</script>

<template>
  <div class="chat-input-wrapper">
    <!-- 已上传文件 -->
    <div v-if="uploadedFiles.length > 0" class="uploaded-files">
      <div
        v-for="(f, i) in uploadedFiles"
        :key="f.token"
        class="file-chip"
      >
        <el-icon><Document /></el-icon>
        <span class="file-name">{{ f.filename }}</span>
        <span class="file-size">({{ (f.size / 1024).toFixed(0) }}KB)</span>
        <button class="file-remove" @click="removeFile(i)">×</button>
      </div>
    </div>

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
      <div class="char-counter" :class="{ over: isOverLimit }">
        {{ charCount }} / {{ MAX_CHARS }}{{ isOverLimit ? ' · 超出部分将转文件发送' : '' }}
      </div>
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <!-- 文件上传按钮 -->
          <label class="upload-btn" :class="{ active: uploading }">
            <el-icon><Upload /></el-icon>
            <input
              type="file"
              multiple
              hidden
              :disabled="disabled || loading"
              @change="handleFileChange"
            />
          </label>

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
          @click="doSend"
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

.uploaded-files {
  max-width: 800px;
  margin: 0 auto 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: #f0f5ff;
  border: 1px solid #adc6ff;
  border-radius: 6px;
  font-size: 12px;
  color: #1d1d1d;
}

.file-chip .file-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-chip .file-size {
  color: #999;
  font-size: 11px;
}

.file-chip .file-remove {
  border: none;
  background: none;
  cursor: pointer;
  color: #999;
  font-size: 14px;
  padding: 0;
  line-height: 1;
}

.file-chip .file-remove:hover {
  color: #f5222d;
}

.upload-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #606266;
  transition: all 0.2s;
  margin-right: 4px;
}

.upload-btn:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}

.upload-btn.active {
  opacity: 0.5;
  pointer-events: none;
}

.char-counter {
  display: flex;
  justify-content: flex-end;
  font-size: 11px;
  color: #bbb;
  margin-top: 4px;
  padding-right: 4px;
}

.char-counter.over {
  color: #fa8c16;
  font-weight: 500;
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
