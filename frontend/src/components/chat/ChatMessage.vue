<script setup lang="ts">
import { renderMarkdown } from '@/utils/markdown'

interface Props {
  type: 'user' | 'assistant'
  content: string
  streaming?: boolean
  contexts?: string[]
}

defineProps<Props>()
const emit = defineEmits<{
  'toggleContext': []
}>()
</script>

<template>
  <div class="message" :class="[type === 'user' ? 'user-message' : 'ai-message']">
    <div class="avatar" :class="{ ai: type === 'assistant' }">
      <svg v-if="type === 'assistant'" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="40" height="40" rx="10" fill="#1d1d1d"/>
        <path d="M12 28V12h4l8 10V12h4v16h-4l-8-10v10h-4z" fill="#fff"/>
      </svg>
      <span v-else>我</span>
    </div>
    <div class="message-body">
      <div class="message-title">{{ type === 'user' ? '你' : '墨问' }}</div>
      <div v-if="streaming && !content" class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <div class="message-content markdown-body" v-html="renderMarkdown(content)"></div>
      <span v-if="streaming && content" class="streaming-cursor" />
      <button
        v-if="contexts && contexts.length > 0 && type === 'assistant'"
        class="context-link"
        @click="emit('toggleContext')"
      >
        <el-icon><Document /></el-icon>
        <span>参考上下文 ({{ contexts.length }})</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  gap: 14px;
  margin-bottom: 24px;
  max-width: 900px;
  margin-left: auto;
  margin-right: auto;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e4e7ed;
  color: #606266;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
}

.avatar.ai {
  background: #000;
  color: #fff;
}

.avatar svg {
  width: 24px;
  height: 24px;
}

.message-body {
  flex: 1;
  min-width: 0;
  padding: 18px 22px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #f0f0f0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.ai-message .message-body {
  background: #f8f8f8;
  border-color: #f0f0f0;
}

.user-message .message-body {
  background: #fff;
  border-color: #e4e7ed;
}

.message-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.message-content {
  font-size: 15px;
  line-height: 1.8;
  color: #1d1d1d;
  word-break: break-word;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-6px);
    opacity: 1;
  }
}

.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  background: #1d1d1d;
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.context-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #909399;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.context-link:hover,
.context-link.active {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}

/* Markdown 渲染样式 */
.markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: #1d1d1d;
  word-break: break-word;
}

.markdown-body :deep(p) {
  margin: 0 0 12px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 20px 0 10px;
  font-weight: 600;
  line-height: 1.4;
}

.markdown-body :deep(h1) { font-size: 1.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; }
.markdown-body :deep(h3) { font-size: 1.15em; }
.markdown-body :deep(h4) { font-size: 1em; }

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 12px;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(li > p) {
  margin: 0;
}

.markdown-body :deep(blockquote) {
  margin: 0 0 12px;
  padding: 8px 16px;
  border-left: 4px solid #e4e7ed;
  background: #fafafa;
  color: #606266;
}

.markdown-body :deep(blockquote p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  border-radius: 4px;
  background: #f5f5f5;
  font-size: 0.9em;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  color: #c7254e;
}

.markdown-body :deep(pre) {
  margin: 0 0 12px;
  padding: 16px;
  border-radius: 8px;
  background: #1d1d1d;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: #f8f8f2;
  font-size: 0.9em;
  line-height: 1.6;
}

.markdown-body :deep(table) {
  margin: 0 0 12px;
  border-collapse: collapse;
  width: 100%;
  font-size: 0.95em;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid #e4e7ed;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #fafafa;
  font-weight: 600;
}

.markdown-body :deep(tr:nth-child(2n)) {
  background: #fafafa;
}

.markdown-body :deep(hr) {
  margin: 16px 0;
  border: none;
  border-top: 1px solid #e4e7ed;
}

.markdown-body :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(em) {
  font-style: italic;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
</style>
