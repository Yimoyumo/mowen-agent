<script setup lang="ts">
interface Props {
  type: 'user' | 'ai'
  title: string
  content: string
  streaming?: boolean
}

defineProps<Props>()

function formatText(text: string): string {
  return text.replace(/\n/g, '<br>')
}
</script>

<template>
  <div class="message" :class="[type === 'user' ? 'user-message' : 'ai-message']">
    <div class="avatar" :class="{ ai: type === 'ai' }">
      <svg v-if="type === 'ai'" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="40" height="40" rx="10" fill="#1d1d1d"/>
        <path d="M12 28V12h4l8 10V12h4v16h-4l-8-10v10h-4z" fill="#fff"/>
      </svg>
      <span v-else>我</span>
    </div>
    <div class="message-body">
      <div class="message-title">{{ title }}</div>
      <div v-if="streaming && !content" class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <div class="message-content" v-html="formatText(content)"></div>
      <span v-if="streaming && content" class="streaming-cursor" />
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
  line-height: 1.8;
  font-size: 15px;
  color: #1d1d1d;
  word-break: break-word;
}

.streaming-cursor {
  display: inline-block;
  width: 6px;
  height: 18px;
  background: #1d1d1d;
  border-radius: 2px;
  margin-left: 4px;
  animation: blink 1s step-end infinite;
  vertical-align: middle;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 24px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  animation: bounce 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-indicator span:nth-child(2) {
  animation-delay: -0.16s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
