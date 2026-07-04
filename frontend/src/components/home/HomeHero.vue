<script setup lang="ts">
const emit = defineEmits<{
  select: [question: string]
}>()

const examples = [
  '洛烟小姐的结局是什么？',
  '洛烟小姐是一个什么样的存在？',
  '洛烟小姐喜欢谁？',
  '安娜是谁？',
]
</script>

<template>
  <div class="hero">
    <h1 class="hero-title">KIMI</h1>
    <p class="hero-subtitle">基于 RAG 的小说智能问答助手</p>
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

.hero-title {
  font-size: 72px;
  font-weight: 700;
  letter-spacing: 8px;
  color: #1d1d1d;
  margin: 0 0 16px;
}

.hero-subtitle {
  font-size: 16px;
  color: #909399;
  margin: 0 0 32px;
}

.example-tags {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  max-width: 600px;
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
  border-color: #409eff;
  color: #409eff;
}
</style>
