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

const apiKey = ref(props.tavilyApiKey)

watch(() => props.tavilyApiKey, (v) => {
  apiKey.value = v
})

function handleSave() {
  emit('save', apiKey.value)
}
</script>

<template>
  <div class="agent-settings">
    <h3>联网搜索配置</h3>
    <p class="desc">
      配置 <a href="https://tavily.com" target="_blank">Tavily</a> API Key 后，Agent 可通过联网搜索工具获取实时信息。
      未配置时联网搜索功能不可用。
    </p>

    <el-input
      v-model="apiKey"
      type="password"
      show-password
      placeholder="tvly-xxxxxxxxxxxxx"
      class="key-input"
    />

    <el-button type="primary" :loading="saving" @click="handleSave" style="margin-top: 12px">
      保存
    </el-button>
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
.key-input {
  width: 100%;
}
</style>
