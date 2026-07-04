<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'
import type { Conversation } from '@/types/api'

interface Props {
  conversations: Conversation[]
  currentId: string | null
}

defineProps<Props>()
const emit = defineEmits<{
  select: [id: string]
  remove: [id: string]
  clear: []
  newConversation: []
}>()
</script>

<template>
  <div class="conv-panel">
    <div class="conv-header">
      <span class="conv-title">对话列表</span>
      <div class="conv-actions">
        <el-button
          :icon="Plus"
          size="small"
          link
          type="primary"
          @click="emit('newConversation')"
        >
          新建
        </el-button>
        <el-button
          v-if="conversations.length > 0"
          :icon="Delete"
          size="small"
          link
          type="danger"
          @click="emit('clear')"
        >
          清空
        </el-button>
      </div>
    </div>

    <div v-if="conversations.length === 0" class="conv-empty">
      暂无对话
    </div>

    <div v-else class="conv-list">
      <div
        v-for="conv in conversations"
        :key="conv.id"
        class="conv-item"
        :class="{ active: conv.id === currentId }"
        @click="emit('select', conv.id)"
      >
        <div class="conv-item-content">
          <div class="conv-item-title">{{ conv.title || '新对话' }}</div>
          <div class="conv-item-meta">
            <span>{{ conv.messages.length }} 条消息</span>
            <span v-if="conv.kbId" class="rag-tag">RAG</span>
          </div>
        </div>
        <button class="conv-item-remove" @click.stop="emit('remove', conv.id)">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.conv-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conv-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
}

.conv-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.conv-actions {
  display: flex;
  gap: 4px;
}

.conv-empty {
  padding: 16px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.conv-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.conv-item:hover {
  background: #f5f7fa;
}

.conv-item.active {
  background: #f0f7ff;
}

.conv-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-item-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #909399;
}

.rag-tag {
  color: #52c41a;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 10px;
}

.conv-item-remove {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: #c0c4cc;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  transition: all 0.2s;
}

.conv-item:hover .conv-item-remove {
  opacity: 1;
}

.conv-item-remove:hover {
  background: #fef0f0;
  color: #f56c6c;
}
</style>
