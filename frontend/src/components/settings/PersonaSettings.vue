<script setup lang="ts">
import { ref, watch } from 'vue'
import type { UserSettings } from '@/types/api'

interface Props {
  settings: UserSettings
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  save: [updates: Partial<UserSettings>]
}>()

const enabled = ref(props.settings.persona.enabled)
const content = ref(props.settings.persona.content)

watch(
  () => props.settings,
  (newVal) => {
    enabled.value = newVal.persona.enabled
    content.value = newVal.persona.content
  },
)

function handleSave() {
  emit('save', {
    persona: {
      enabled: enabled.value,
      content: content.value,
    },
  } as any)
}

const examples = [
  '你是一个幽默的程序员助手，回答时经常用编程相关的比喻',
  '你是一个温柔的大姐姐，说话轻声细语，总是鼓励用户',
  '你是一个严谨的学术导师，回答注重逻辑和引用来源',
  '你是一个猫娘助手，说话会带"喵"，性格活泼可爱',
]
</script>

<template>
  <div class="persona-settings">
    <h2 class="section-title">人格设定</h2>
    <p class="section-desc">
      自定义 Agent 的角色性格。启用后，你的描述会注入到系统提示词中，
      影响助手的回答风格和行为方式。
    </p>

    <el-card shadow="never" class="settings-card">
      <div class="persona-header">
        <span class="label-text">启用自定义人格</span>
        <el-switch v-model="enabled" />
      </div>

      <el-divider />

      <div class="persona-content-area">
        <span class="label-text">角色描述</span>
        <el-input
          v-model="content"
          type="textarea"
          :rows="8"
          placeholder="描述你希望助手扮演的角色、性格、说话风格等…"
          :disabled="!enabled"
          maxlength="2000"
          show-word-limit
        />
      </div>

      <el-divider />

      <!-- 示例 -->
      <div v-if="!content" class="examples">
        <span class="examples-title">参考示例：</span>
        <div
          v-for="(ex, i) in examples"
          :key="i"
          class="example-item"
          @click="content = ex"
        >
          {{ ex }}
        </div>
      </div>

      <el-divider />

      <div class="save-area">
        <el-button type="primary" :loading="saving" @click="handleSave">
          保存
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
  line-height: 1.6;
}

.settings-card {
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.persona-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.label-text {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  display: block;
  margin-bottom: 8px;
}

.examples {
  margin-top: 8px;
}

.examples-title {
  font-size: 13px;
  color: #909399;
  display: block;
  margin-bottom: 8px;
}

.example-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 8px;
  background: #f5f7fa;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;
}

.example-item:hover {
  background: #ecf5ff;
  color: #409eff;
}

.save-area {
  display: flex;
  justify-content: flex-end;
}
</style>
