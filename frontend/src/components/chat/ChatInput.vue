<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient } from '@/api/config'
import { get_model_context } from '@/api/configApi'

const MAX_CHARS = 8000   // 单条消息最大字符数，超过自动转文件

interface Props {
  modelValue: string
  loading: boolean
  disabled: boolean
  knowledgeBases: { id: string; name: string }[]
  currentKbId: string | null
  modelOptions?: string[]
  activeModel?: string
  modelVisionMap?: Record<string, boolean>
}

const props = withDefaults(defineProps<Props>(), {
  modelOptions: () => [],
  activeModel: '',
  modelVisionMap: () => ({}),
})
const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [uploadedFiles: { token: string; filename: string }[]]
  stop: []
  selectKb: [kbId: string]
  selectModel: [modelRef: string]
}>()

const charCount = computed(() => props.modelValue.length)
const isOverLimit = computed(() => charCount.value > MAX_CHARS)
const hasContent = computed(() => props.modelValue.trim().length > 0)
const canSend = computed(() => hasContent.value && !props.loading && !props.disabled)

// 当前模型的上下文窗口信息
const modelCtx = ref<{ context_window: number; max_output: number }>({ context_window: 0, max_output: 0 })

async function loadModelCtx(modelRef: string) {
  if (!modelRef) {
    modelCtx.value = { context_window: 0, max_output: 0 }
    return
  }
  try {
    const info = await get_model_context(modelRef)
    modelCtx.value = { context_window: info.context_window, max_output: info.max_output }
  } catch {
    modelCtx.value = { context_window: 0, max_output: 0 }
  }
}

watch(() => props.activeModel, (m) => loadModelCtx(m), { immediate: true })

// 格式化 token 数为可读文字
function fmtTokens(n: number): string {
  if (n <= 0) return ''
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (n >= 1000) return `${Math.round(n / 1024)}K`
  return String(n)
}

// 为每个模型选项生成 label（附带上下文窗口大小）
function modelLabel(m: string): string {
  return m
}

// 文件上传
const uploadedFiles = ref<{ token: string; filename: string; size: number; is_image: boolean }[]>([])
const uploading = ref(false)

async function uploadOneFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await apiClient.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  uploadedFiles.value.push(res.data)
}

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files) return

  uploading.value = true
  for (const file of Array.from(files)) {
    try { await uploadOneFile(file) } catch { /* ignore */ }
  }
  uploading.value = false
  input.value = ''  // reset so same file can be re-uploaded
}

async function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    // 剪贴板中的图片
    if (item.type.startsWith('image/')) {
      e.preventDefault()  // 阻止默认粘贴行为（避免粘贴图片二进制乱码）
      const file = item.getAsFile()
      if (!file) continue
      // 如果没文件名，生成一个
      if (!file.name || file.name === 'image.png') {
        const ext = item.type.split('/')[1] || 'png'
        const renamed = new File([file], `paste_${Date.now()}.${ext}`, { type: item.type })
        uploading.value = true
        try { await uploadOneFile(renamed) } catch { /* ignore */ }
        uploading.value = false
      } else {
        uploading.value = true
        try { await uploadOneFile(file) } catch { /* ignore */ }
        uploading.value = false
      }
    }
  }
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
  const firstLine = (text.trim().split(/\n/)[0] ?? '').slice(0, 40).replace(/[^\w\u4e00-\u9fff]/g, '_')
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
      files.push({ ...uploaded, size: 0 })
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
        <template v-if="f.is_image">
          <img :src="`/api/uploads/${f.token}/${f.filename}`" class="file-chip-thumb" />
        </template>
        <el-icon v-else><Document /></el-icon>
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
        @paste="handlePaste"
      />
      <div class="char-counter" :class="{ over: isOverLimit }">
        {{ charCount }} / {{ MAX_CHARS }}{{ isOverLimit ? ' · 超出部分将转文件发送' : '' }}
      </div>
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <!-- 文件上传 -->
          <label class="upload-btn" :class="{ active: uploading }">
            <el-icon><Upload /></el-icon>
            <input type="file" multiple hidden :disabled="disabled || loading" @change="handleFileChange" />
          </label>

          <!-- 模型切换 -->
          <el-select
            v-if="modelOptions.length > 0"
            :model-value="activeModel"
            size="small"
            class="model-select"
            popper-class="model-select-popper"
            @change="(val: string) => emit('selectModel', val)"
          >
            <template #label>
              <span class="model-label-text">{{ activeModel.split('/').pop() || activeModel }}</span>
              <el-tag v-if="modelVisionMap[activeModel]" size="small" type="success" class="vision-badge">👁️</el-tag>
              <span v-if="modelCtx.context_window > 0" class="model-ctx-badge">
                {{ fmtTokens(modelCtx.context_window) }}
              </span>
            </template>
            <el-option
              v-for="m in modelOptions"
              :key="m"
              :label="m"
              :value="m"
            >
              <span>{{ m }}</span>
              <el-tag v-if="modelVisionMap[m]" size="small" type="success" class="vision-tag">👁️ 视觉</el-tag>
            </el-option>
          </el-select>

          <!-- 知识库选择 -->
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
      <span class="input-tip">Enter 发送 · Shift+Enter 换行 · Ctrl+V 粘贴图片{{ currentKbId ? ' · RAG 增强' : '' }}</span>
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

.file-chip-thumb {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
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

.model-select {
  width: 220px;
}

.model-select :deep(.el-select__selection-wrapper) {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}

.model-label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.model-ctx-badge {
  font-size: 11px;
  color: #409eff;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  padding: 1px 6px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
}

.vision-badge {
  font-size: 11px;
  padding: 1px 4px;
  flex-shrink: 0;
}

.vision-tag {
  margin-left: 6px;
}

.ctx-info {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
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
