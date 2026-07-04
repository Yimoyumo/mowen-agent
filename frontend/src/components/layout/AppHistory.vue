<script setup lang="ts">
import type { AskResponse } from '@/types/api'

interface Props {
  history: AskResponse[]
  current: AskResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  select: [item: AskResponse]
}>()

function isActive(item: AskResponse) {
  return props.current?.question === item.question
}
</script>

<template>
  <div class="history-section">
    <div class="history-header">
      <el-icon><Clock /></el-icon>
      <span>历史记录 ({{ history.length }})</span>
    </div>
    <div class="history-list">
      <div
        v-for="(item, index) in history"
        :key="index"
        class="history-item"
        :class="{ active: isActive(item) }"
        @click="emit('select', item)"
      >
        <p class="history-question">{{ item.question }}</p>
        <p class="history-answer">{{ item.answer.slice(0, 50) }}...</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-section {
  padding: 0 4px;
}

.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #909399;
  padding: 8px 12px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item {
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:hover,
.history-item.active {
  background: #f5f5f5;
}

.history-question {
  margin: 0 0 4px;
  font-weight: 500;
  color: #1d1d1d;
  font-size: 13px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-answer {
  margin: 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
