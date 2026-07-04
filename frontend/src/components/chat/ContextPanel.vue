<script setup lang="ts">
import { renderMarkdown } from '@/utils/markdown'

interface Props {
  contexts: string[]
  visible: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <Transition name="slide">
    <aside v-if="visible" class="context-panel">
      <div class="context-header">
        <h3>
          <el-icon><Document /></el-icon>
          参考上下文
        </h3>
        <button class="close-btn" @click="emit('close')">
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div class="context-list">
        <div v-if="contexts.length === 0" class="empty-context">暂无参考上下文</div>
        <div v-for="(ctx, idx) in contexts" :key="idx" class="context-item">
          <div class="context-index">{{ idx + 1 }}</div>
          <div class="context-content markdown-body" v-html="renderMarkdown(ctx)"></div>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.context-panel {
  width: 420px;
  min-width: 420px;
  height: 100%;
  background: #fff;
  border-left: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.context-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.context-header h3 {
  margin: 0;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1d1d1d;
}

.close-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #1d1d1d;
}

.context-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
}

.empty-context {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #909399;
  font-size: 14px;
}

.context-item {
  display: flex;
  gap: 10px;
  padding: 14px;
  margin-bottom: 12px;
  background: #fff;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.7;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.context-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #000;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.context-content {
  color: #606266;
  word-break: break-word;
  flex: 1;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

@media (max-width: 1024px) {
  .context-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 2000;
    width: 85vw;
    min-width: 280px;
  }
}

/* Markdown 渲染样式（与 ChatMessage 一致） */
.markdown-body {
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
  word-break: break-word;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 12px 0 6px;
  font-weight: 600;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 8px;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: #f5f5f5;
  font-size: 0.9em;
  font-family: 'SFMono-Regular', Consolas, monospace;
  color: #c7254e;
}

.markdown-body :deep(pre) {
  margin: 0 0 8px;
  padding: 12px;
  border-radius: 6px;
  background: #1d1d1d;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: #f8f8f2;
}

.markdown-body :deep(blockquote) {
  margin: 0 0 8px;
  padding: 6px 12px;
  border-left: 3px solid #e4e7ed;
  color: #909399;
}

.markdown-body :deep(table) {
  margin: 0 0 8px;
  border-collapse: collapse;
  width: 100%;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 4px 8px;
  border: 1px solid #e4e7ed;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}
</style>
