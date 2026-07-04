<script setup lang="ts">
interface Props {
  contexts: string[]
  visible: boolean
}

defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()

function formatText(text: string): string {
  return text.replace(/\n/g, '<br>')
}
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
          <div class="context-content" v-html="formatText(ctx)"></div>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.context-panel {
  width: 420px;
  min-width: 420px;
  height: 100vh;
  background: #fff;
  border-left: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
</style>
