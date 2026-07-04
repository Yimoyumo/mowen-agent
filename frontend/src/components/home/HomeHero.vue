<script setup lang="ts">
const emit = defineEmits<{
  select: [question: string]
}>()

const examples = [
  '你好，介绍一下你自己',
  '帮我写一首关于春天的诗',
  '解释一下什么是 RAG 技术',
  '用 Python 实现快速排序',
]
</script>

<template>
  <div class="hero">
    <div class="brand">
      <div class="brand-mark">
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="40" height="40" rx="10" fill="#1d1d1d"/>
          <path d="M12 28V12h4l8 10V12h4v16h-4l-8-10v10h-4z" fill="#fff"/>
        </svg>
      </div>
      <h1 class="hero-title">墨问</h1>
    </div>
    <p class="hero-subtitle">你的智能 AI 助手 · 支持多轮对话与知识库增强</p>
    <div class="example-tags">
      <span
        v-for="example in examples"
        :key="example"
        class="example-tag"
        @click="emit('select', example)"
      >
        {{ example }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.brand-mark {
  width: 48px;
  height: 48px;
}

.brand-mark svg {
  width: 100%;
  height: 100%;
}

.hero-title {
  font-size: 56px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #1d1d1d;
  margin: 0;
}

.hero-subtitle {
  font-size: 16px;
  color: #606266;
  margin: 0 0 36px;
}

.example-tags {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  max-width: 640px;
}

.example-tag {
  padding: 10px 18px;
  border-radius: 999px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}
</style>
