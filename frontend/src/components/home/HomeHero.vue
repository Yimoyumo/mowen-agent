<script setup lang="ts">
const emit = defineEmits<{
  select: [question: string]
}>()

const examples = [
  '洛烟小姐的结局是什么？',
  '这本书的主要角色有哪些？',
  '介绍一下小说的世界观',
  '终章讲了什么？',
]

interface Props {
  kbSelected: boolean
}

defineProps<Props>()
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
    <p class="hero-subtitle">上传文档，提出问题，让 AI 帮你读懂每一页</p>
    <p v-if="!kbSelected" class="hero-tip">
      <el-icon><Info-Filled /></el-icon>
      请先从左侧面板选择一个知识库
    </p>
    <div v-else class="example-tags">
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
  background: #fff;
  border: 1px solid #e4e7ed;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
  background: #f5f5f5;
}

.hero-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  border-radius: 999px;
  background: #fdf6ec;
  border: 1px solid #f5dab1;
  color: #e6a23c;
  font-size: 14px;
  margin: 0;
}

.hero-tip .el-icon {
  font-size: 16px;
}
</style>
