<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElInput, ElButton } from 'element-plus'

const props = defineProps<{
  tavilyApiKey: string
  saving: boolean
}>()

const emit = defineEmits<{
  save: [key: string]
}>()

const apiKey = ref('')

// 不回显已保存的密钥：只通过 props.tavilyApiKey 判断是否已配置，
// 用于显示占位提示"已保存 (可修改)"。点小眼睛只能看到空输入框，保护密钥安全。

watch(() => props.tavilyApiKey, () => {
  // 后端更新后清空输入框（保存成功 / 父组件刷新）
  apiKey.value = ''
})

function handleSave() {
  emit('save', apiKey.value.trim())
}
</script>

<template>
  <div class="agent-settings">
    <h3>联网搜索配置</h3>
    <p class="desc">
      配置 <a href="https://tavily.com" target="_blank">Tavily</a> API Key 后，Agent 可通过联网搜索工具获取实时信息。
      未配置时联网搜索功能不可用。
    </p>

    <div class="key-row">
      <el-input
        v-model="apiKey"
        type="password"
        show-password
        size="default"
        :placeholder="tavilyApiKey ? '已保存 (可修改)' : '输入 Tavily API Key'"
        @keydown.enter="handleSave"
      >
        <template #prepend><el-icon><Key /></el-icon></template>
      </el-input>
      <el-button type="primary" :loading="saving" @click="handleSave">保存 Key</el-button>
    </div>
  </div>
</template>

<style scoped>
.agent-settings {
  max-width: 500px;
}
.agent-settings h3 {
  margin: 0 0 8px;
}
.desc {
  color: #909399;
  font-size: 13px;
  margin-bottom: 16px;
  line-height: 1.6;
}
.desc a {
  color: var(--el-color-primary);
}
.key-row {
  display: flex;
  gap: 8px;
}
</style>
