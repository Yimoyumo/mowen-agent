<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Plus, Upload, Refresh, Delete, Document, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import { getKnowledgeBaseDocuments } from '@/api/chat'
import type { KnowledgeBaseDocumentInfo } from '@/types/api'

interface Props {
  creating: boolean
  building: boolean
  uploading: boolean
  kbTypes: { value: string; label: string }[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  create: [name: string, description: string, kbType: string]
  delete: [kbId: string]
  build: [kbId: string]
  upload: [kbId: string, file: File]
  select: [kbId: string]
}>()

const store = useKnowledgeBaseStore()
const showCreateDialog = ref(false)
const newKbName = ref('')
const newKbDesc = ref('')
const newKbType = ref('general')
const fileInput = ref<HTMLInputElement | null>(null)
const expandedKbId = ref<string | null>(null)
const kbDocs = ref<Record<string, KnowledgeBaseDocumentInfo[]>>({})
const kbDocsLoading = ref<Record<string, boolean>>({})

const canCreate = computed(() => newKbName.value.trim().length > 0 && !props.creating)

function openCreate() {
  newKbName.value = ''
  newKbDesc.value = ''
  newKbType.value = 'general'
  showCreateDialog.value = true
}

function confirmCreate() {
  emit('create', newKbName.value.trim(), newKbDesc.value.trim(), newKbType.value)
  showCreateDialog.value = false
}

function triggerUpload(kbId: string) {
  store.setCurrentKbId(kbId)
  fileInput.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  const kbId = store.currentKbId
  if (file && kbId) {
    emit('upload', kbId, file)
    target.value = ''
  }
}

function kbTypeLabel(value: string) {
  return props.kbTypes.find((t) => t.value === value)?.label ?? value
}

function toggleDocs(kbId: string) {
  if (expandedKbId.value === kbId) {
    expandedKbId.value = null
    return
  }
  expandedKbId.value = kbId
  void loadDocs(kbId)
}

async function loadDocs(kbId: string) {
  if (kbDocs.value[kbId] || kbDocsLoading.value[kbId]) return
  kbDocsLoading.value[kbId] = true
  try {
    const res = await getKnowledgeBaseDocuments(kbId)
    kbDocs.value[kbId] = res.documents
  } catch (err) {
    const axiosErr = err as AxiosError<{ detail?: string }>
    ElMessage.error(axiosErr.response?.data?.detail || '加载文档信息失败')
  } finally {
    kbDocsLoading.value[kbId] = false
  }
}

watch(
  () => store.currentKbId,
  (kbId) => {
    if (kbId) {
      void loadDocs(kbId)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="kb-panel">
    <div class="kb-header">
      <span class="kb-title">知识库</span>
      <el-button
        :icon="Plus"
        size="small"
        circle
        :loading="creating"
        @click="openCreate"
      />
    </div>

    <div v-if="store.loading" class="kb-loading">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="store.knowledgeBases.length === 0" class="kb-empty">
      暂无知识库，点击右上角 + 创建
    </div>

    <div v-else class="kb-list">
      <div
        v-for="kb in store.knowledgeBases"
        :key="kb.id"
        class="kb-item-wrapper"
        :class="{ active: kb.id === store.currentKbId }"
      >
        <div
          class="kb-item"
          @click="emit('select', kb.id)"
        >
          <div class="kb-item-main">
            <el-icon class="kb-item-icon"><Document /></el-icon>
            <div class="kb-item-info">
              <div class="kb-item-name">{{ kb.name }}</div>
              <div class="kb-item-meta">
                <el-tag size="small" effect="plain">{{ kbTypeLabel(kb.kb_type) }}</el-tag>
              </div>
            </div>
          </div>

          <div class="kb-item-actions" @click.stop>
            <el-tooltip content="查看文档" placement="top">
              <el-button
                :icon="expandedKbId === kb.id ? ArrowDown : ArrowRight"
                size="small"
                link
                :class="{ active: expandedKbId === kb.id }"
                @click="toggleDocs(kb.id)"
              />
            </el-tooltip>
            <el-tooltip content="上传文档" placement="top">
              <el-button
                :icon="Upload"
                size="small"
                link
                :loading="uploading && kb.id === store.currentKbId"
                :disabled="uploading || building"
                @click="triggerUpload(kb.id)"
              />
            </el-tooltip>
            <el-tooltip content="重建向量库" placement="top">
              <el-button
                :icon="Refresh"
                size="small"
                link
                :loading="building && kb.id === store.currentKbId"
                :disabled="uploading || building"
                @click="emit('build', kb.id)"
              />
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <el-button
                :icon="Delete"
                size="small"
                link
                type="danger"
                :disabled="uploading || building"
                @click="emit('delete', kb.id)"
              />
            </el-tooltip>
          </div>
        </div>

        <div v-if="expandedKbId === kb.id" class="kb-docs" @click.stop>
          <div v-if="kbDocsLoading[kb.id]" class="kb-docs-loading">
            <el-skeleton :rows="2" animated />
          </div>
          <div v-else-if="!kbDocs[kb.id] || kbDocs[kb.id]!.length === 0" class="kb-docs-empty">
            暂无文档
          </div>
          <div v-else class="kb-docs-list">
            <div
              v-for="doc in kbDocs[kb.id]!"
              :key="doc.file_name"
              class="kb-doc-item"
            >
              <div class="kb-doc-main">
                <el-icon class="kb-doc-icon"><Document /></el-icon>
                <span class="kb-doc-name" :title="doc.file_name">{{ doc.file_name }}</span>
              </div>
              <div class="kb-doc-meta">
                <el-tag size="small" effect="plain" type="info">{{ doc.chunks }} 块</el-tag>
                <el-tag
                  v-if="doc.chapters.length > 0"
                  size="small"
                  effect="plain"
                  type="success"
                >
                  {{ doc.chapters.length }} 章节
                </el-tag>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept=".txt,.md,.json,.csv"
      class="hidden-file-input"
      @change="handleFileChange"
    />

    <el-dialog
      v-model="showCreateDialog"
      title="新建知识库"
      width="360px"
      align-center
    >
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="newKbName" placeholder="请输入知识库名称" maxlength="32" show-word-limit />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="newKbType" placeholder="请选择知识库类型" style="width: 100%">
            <el-option
              v-for="t in props.kbTypes"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述（可选）">
          <el-input
            v-model="newKbDesc"
            type="textarea"
            :rows="3"
            placeholder="简单描述该知识库的用途"
            maxlength="100"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!canCreate" @click="confirmCreate">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.kb-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
}

.kb-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.kb-loading,
.kb-empty {
  padding: 16px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.kb-list {
  display: flex;
  flex-direction: column;
  max-height: 280px;
  overflow-y: auto;
}

.kb-item-wrapper {
  border-radius: 10px;
  transition: background 0.2s;
}

.kb-item-wrapper:hover {
  background: #f5f7fa;
}

.kb-item-wrapper.active {
  background: #f0f7ff;
}

.kb-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
}

.kb-item-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.kb-item-icon {
  font-size: 18px;
  color: #409eff;
  flex-shrink: 0;
}

.kb-item-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kb-item-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  word-break: break-all;
  line-height: 1.4;
}

.kb-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.kb-item-desc {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
  line-height: 1.4;
}

.kb-item-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.kb-item-wrapper:hover .kb-item-actions,
.kb-item-wrapper.active .kb-item-actions {
  opacity: 1;
}

.kb-item-actions .el-button.active {
  color: #1d1d1d;
}

.kb-docs {
  padding: 0 12px 10px 40px;
}

.kb-docs-loading,
.kb-docs-empty {
  padding: 8px 0;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.kb-docs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kb-doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}

.kb-doc-item:last-child {
  border-bottom: none;
}

.kb-doc-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.kb-doc-icon {
  font-size: 14px;
  color: #909399;
  flex-shrink: 0;
}

.kb-doc-name {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kb-doc-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.hidden-file-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
  visibility: hidden;
}
</style>
