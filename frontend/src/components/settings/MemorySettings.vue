<script setup lang="ts">
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { MemoryItem } from '@/types/api'

interface Props {
  memories: MemoryItem[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  add: [type: string, content: string, callback: (ok: boolean) => void]
  update: [id: string, type: string, content: string, callback: (ok: boolean) => void]
  delete: [id: string]
  clear: []
}>()

// 添加记忆
const newType = ref('fact')
const newContent = ref('')

function handleAdd() {
  if (!newContent.value.trim()) return
  emit('add', newType.value, newContent.value.trim(), (ok: boolean) => {
    if (ok) {
      newContent.value = ''
    }
  })
}

// 编辑记忆
const editingId = ref<string | null>(null)
const editType = ref('fact')
const editContent = ref('')

function startEdit(mem: MemoryItem) {
  editingId.value = mem.id
  editType.value = mem.type
  editContent.value = mem.content
}

function cancelEdit() {
  editingId.value = null
}

function saveEdit() {
  if (!editingId.value || !editContent.value.trim()) return
  emit('update', editingId.value, editType.value, editContent.value.trim(), (ok: boolean) => {
    if (ok) {
      editingId.value = null
    }
  })
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定要清空所有记忆吗？此操作不可恢复。', '清空确认', {
      type: 'warning',
    })
    emit('clear')
  } catch {
    // cancelled
  }
}

async function handleDelete(id: string) {
  try {
    await ElMessageBox.confirm('确定要删除这条记忆吗？', '删除确认', { type: 'warning' })
    emit('delete', id)
  } catch {
    // cancelled
  }
}

const typeColors: Record<string, string> = {
  fact: 'primary',
  preference: 'success',
  summary: 'warning',
}

const typeLabels: Record<string, string> = {
  fact: '事实',
  preference: '偏好',
  summary: '摘要',
}
</script>

<template>
  <div class="memory-settings">
    <h2 class="section-title">模型记忆</h2>
    <p class="section-desc">
      AI 助手从对话中自动提取的长期记忆。你可以在此查看、编辑、添加或删除记忆，
      这些记忆会影响助手对你的理解和回答。
    </p>

    <!-- 添加记忆 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-header-text">添加记忆</span>
      </template>
      <div class="add-memory-area">
        <div class="add-memory-row">
          <el-select v-model="newType" style="width: 120px">
            <el-option label="事实" value="fact" />
            <el-option label="偏好" value="preference" />
            <el-option label="摘要" value="summary" />
          </el-select>
          <el-input
            v-model="newContent"
            placeholder="输入记忆内容，如：用户擅长 Python 后端开发"
            @keydown.enter="handleAdd"
          />
          <el-button type="primary" @click="handleAdd">添加</el-button>
        </div>
      </div>
    </el-card>

    <!-- 记忆列表 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span class="card-header-text">
            记忆列表
            <el-badge :value="memories.length" :max="99" class="mem-count-badge" />
          </span>
          <el-button
            v-if="memories.length > 0"
            text
            type="danger"
            size="small"
            @click="handleClear"
          >
            清空全部
          </el-button>
        </div>
      </template>

      <div v-if="memories.length === 0" class="empty-state">
        暂无记忆，AI 助手会在对话中自动学习
      </div>

      <div v-else class="memory-list">
        <div
          v-for="mem in memories"
          :key="mem.id"
          class="memory-item"
        >
          <!-- 编辑模式 -->
          <template v-if="editingId === mem.id">
            <div class="memory-edit">
              <el-select v-model="editType" size="small" style="width: 100px">
                <el-option label="事实" value="fact" />
                <el-option label="偏好" value="preference" />
                <el-option label="摘要" value="summary" />
              </el-select>
              <el-input
                v-model="editContent"
                type="textarea"
                :rows="2"
                size="small"
              />
              <div class="edit-actions">
                <el-button size="small" @click="cancelEdit">取消</el-button>
                <el-button size="small" type="primary" @click="saveEdit">保存</el-button>
              </div>
            </div>
          </template>

          <!-- 展示模式 -->
          <template v-else>
            <div class="memory-display">
              <el-tag :type="typeColors[mem.type]" size="small">
                {{ typeLabels[mem.type] || mem.type }}
              </el-tag>
              <span class="memory-content">{{ mem.content }}</span>
            </div>
            <div class="memory-actions">
              <el-button text size="small" @click="startEdit(mem)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text type="danger" size="small" @click="handleDelete(mem.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </template>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
  line-height: 1.6;
}

.settings-card {
  margin-bottom: 16px;
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-text {
  font-size: 15px;
  font-weight: 500;
}

.mem-count-badge {
  margin-left: 8px;
}

.add-memory-row {
  display: flex;
  gap: 8px;
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: #c0c4cc;
  font-size: 14px;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f5f7fa;
  gap: 12px;
}

.memory-display {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.memory-content {
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
}

.memory-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.memory-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
