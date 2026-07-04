<script setup lang="ts">
import { Delete } from '@element-plus/icons-vue'
import type { AskResponse } from '@/types/api'

interface Props {
  history: AskResponse[]
  current: AskResponse | null
}

defineProps<Props>()
const emit = defineEmits<{
  select: [item: AskResponse]
  remove: [index: number]
  clear: []
}>()

function truncate(text: string, max: number) {
  return text.length > max ? text.slice(0, max) + '…' : text
}
</script>

<template>
  <div class="history-panel">
    <div class="history-header">
      <span class="history-title">对话记录</span>
      <el-button
        v-if="history.length > 0"
        :icon="Delete"
        size="small"
        link
        type="danger"
        @click="emit('clear')"
      >
        清空
      </el-button>
    </div>

    <div v-if="history.length === 0" class="history-empty">
      暂无对话记录
    </div>

    <div v-else class="history-list">
      <div
        v-for="(item, idx) in history"
        :key="idx"
        class="history-item"
        :class="{ active: current === item }"
        @click="emit('select', item)"
      >
        <div class="history-item-content">
          <div class="history-item-question">{{ truncate(item.question, 40) }}</div>
          <div v-if="item.answer" class="history-item-answer">{{ truncate(item.answer.replace(/\n/g, ' '), 50) }}</div>
        </div>
        <button class="history-item-remove" @click.stop="emit('remove', idx)">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
}

.history-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.history-empty {
  padding: 16px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.history-item:hover {
  background: #f5f7fa;
}

.history-item.active {
  background: #f0f7ff;
}

.history-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item-question {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  line-height: 1.4;
  word-break: break-all;
}

.history-item-answer {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  word-break: break-all;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.history-item-remove {
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

.history-item:hover .history-item-remove {
  opacity: 1;
}

.history-item-remove:hover {
  background: #fef0f0;
  color: #f56c6c;
}
</style>
