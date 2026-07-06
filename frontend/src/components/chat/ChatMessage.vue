<script setup lang="ts">
import { ref, computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import type { MessageSegment } from '@/types/api'

interface Props {
  type: 'user' | 'assistant'
  content: string
  streaming?: boolean
  contexts?: string[]
  reasoning?: string
  segments?: MessageSegment[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'toggleContext': []
}>()

const showReasoning = ref(true)
const expandedTools = ref<Set<number>>(new Set())

const toolLabels: Record<string, string> = {
  sandbox_run: '执行命令',
  sandbox_write_file: '写入文件',
  sandbox_read_file: '读取文件',
  sandbox_list_files: '查看目录',
  sandbox_export_file: '导出文件',
  search_knowledge_base: '搜索知识库',
  search_web: '联网搜索',
}

function toolLabel(name: string) {
  return toolLabels[name] ?? name
}

function toolEmoji(name: string) {
  if (name === 'sandbox_run') return '⚡'
  if (name === 'search_web') return '🌐'
  if (name === 'search_knowledge_base') return '📚'
  return '🔧'
}

function toggleTool(i: number) {
  if (expandedTools.value.has(i)) expandedTools.value.delete(i)
  else expandedTools.value.add(i)
}

// segments 中的全局索引（只给 tool segment 记数）
function toolGlobalIndex(segIndex: number) {
  if (!props.segments) return 0
  let count = 0
  for (let i = 0; i < segIndex; i++) {
    const seg = props.segments[i]
    if (seg && seg.type === 'tool') count++
  }
  return count
}

const hasRunningTool = computed(() =>
  props.segments?.some(s => s.type === 'tool' && s.status === 'running')
)
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

      <!-- 推理过程区域（可折叠） -->
      <div v-if="reasoning" class="reasoning-section">
        <button class="reasoning-toggle" @click="showReasoning = !showReasoning">
          <el-icon class="reasoning-icon" :class="{ expanded: showReasoning }"><ArrowRight /></el-icon>
          <span>{{ showReasoning ? '收起推理过程' : '展开推理过程' }}</span>
          <span v-if="streaming && !content" class="reasoning-status">思考中…</span>
        </button>
        <div v-if="showReasoning" class="reasoning-content markdown-body" v-html="renderMarkdown(reasoning)"></div>
      </div>

      <!-- 交错渲染文本和工具调用 -->
      <template v-if="segments && segments.length > 0">
        <template v-for="(seg, i) in segments" :key="i">
          <!-- 文本片段 -->
          <div v-if="seg.type === 'text'" class="message-content markdown-body" v-html="renderMarkdown(seg.content)"></div>

          <!-- 工具调用片段 -->
          <div
            v-else-if="seg.type === 'tool'"
            class="tool-call-item"
            :class="{ running: seg.status === 'running' }"
          >
            <button class="tool-call-header" @click="toggleTool(toolGlobalIndex(i))">
              <el-icon class="tool-icon" :class="{ expanded: expandedTools.has(toolGlobalIndex(i)) }"><ArrowRight /></el-icon>
              <span class="tool-icon-icon">{{ toolEmoji(seg.tool) }}</span>
              <span class="tool-name">{{ toolLabel(seg.tool) }}</span>
              <span v-if="seg.status === 'running'" class="tool-status running">
                <span class="dot-flashing"></span>执行中
              </span>
              <span v-else class="tool-status done">✓ 完成</span>
            </button>
            <div v-if="expandedTools.has(toolGlobalIndex(i))" class="tool-call-detail">
              <div v-if="seg.input" class="tool-input">
                <span class="detail-label">输入:</span>
                <pre>{{ seg.input }}</pre>
              </div>
              <div v-if="seg.output" class="tool-output">
                <span class="detail-label">输出:</span>
                <pre>{{ seg.output }}</pre>
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- 没有 segments 时走老逻辑（向后兼容） -->
      <template v-else>
        <div class="message-content markdown-body" v-html="renderMarkdown(content)"></div>
      </template>

      <span v-if="streaming && content" class="streaming-cursor" />
      <div v-if="streaming && !content && !reasoning && !hasRunningTool" class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
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

/* 推理过程折叠区域 */
.reasoning-section {
  margin-bottom: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.reasoning-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: #fafafa;
  color: #909399;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.reasoning-toggle:hover {
  background: #f0f0f0;
}

.reasoning-icon {
  transition: transform 0.2s;
  font-size: 12px;
}

.reasoning-icon.expanded {
  transform: rotate(90deg);
}

.reasoning-status {
  color: #409eff;
  font-size: 11px;
}

.reasoning-content {
  padding: 12px 16px;
  font-size: 13px;
  color: #909399;
  line-height: 1.7;
  border-top: 1px solid #e8e8e8;
  max-height: 400px;
  overflow-y: auto;
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

/* 工具调用状态 */
.tool-calls {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0;
}

.tool-call-item {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  background: #fafafa;
}

.tool-call-item.running {
  border-color: #c0c4cc;
  background: #f5f7fa;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  width: 100%;
  text-align: left;
}

.tool-call-header:hover {
  background: #f0f0f0;
}

.tool-icon {
  transition: transform 0.2s;
  font-size: 12px;
  color: #909399;
}

.tool-icon.expanded {
  transform: rotate(90deg);
}

.tool-icon-icon {
  font-size: 14px;
}

.tool-name {
  font-weight: 500;
  flex: 1;
}

.tool-status {
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-status.running {
  color: #409eff;
}

.tool-status.done {
  color: #67c23a;
}

.dot-flashing {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #409eff;
  animation: dotFlashing 0.8s infinite alternate;
}

@keyframes dotFlashing {
  to { opacity: 0.3; }
}

.tool-call-detail {
  padding: 8px 10px;
  border-top: 1px solid #e4e7ed;
  font-size: 12px;
}

.tool-input,
.tool-output {
  margin-bottom: 6px;
}

.tool-input pre,
.tool-output pre {
  margin: 4px 0 0;
  padding: 6px 8px;
  background: #fff;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.detail-label {
  color: #909399;
  font-weight: 500;
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
