<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { EmbeddingConfig } from '@/types/api'

interface Props {
  config: EmbeddingConfig | null
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  setModel: [modelRef: string]
  setCustom: [config: { enabled?: boolean; base_url?: string; api_key?: string; model?: string }]
}>()

// ---- 厂商模型选择 ----
const selectedRef = ref('')

watch(
  () => props.config,
  (cfg) => {
    if (cfg) {
      selectedRef.value = cfg.embedding_model || ''
    }
  },
  { immediate: true },
)

const currentDisplay = computed(() => {
  if (!props.config) return '未加载'
  const custom = props.config.embedding_custom
  if (custom?.enabled && custom.model) {
    return `自定义: ${custom.model}`
  }
  if (!props.config.embedding_model) return '自动推断（从已配置厂商中查找）'
  return props.config.embedding_model
})

const hasAvailable = computed(() => {
  return props.config && props.config.available_models.length > 0
})

const noKeyModels = computed(() => {
  if (!props.config) return []
  return props.config.available_models.filter((m) => !m.has_api_key)
})

function handleSave() {
  emit('setModel', selectedRef.value)
}

function handleClear() {
  selectedRef.value = ''
  emit('setModel', '')
}

// ---- 自定义向量模型 ----
const customEnabled = ref(false)
const customBaseUrl = ref('')
const customApiKey = ref('')
const customModel = ref('')

watch(
  () => props.config?.embedding_custom,
  (custom) => {
    if (custom) {
      customEnabled.value = custom.enabled
      customBaseUrl.value = custom.base_url
      customApiKey.value = ''  // 不回显 API Key
      customModel.value = custom.model
    }
  },
  { immediate: true },
)

function handleSaveCustom() {
  const config: { enabled?: boolean; base_url?: string; api_key?: string; model?: string } = {
    enabled: customEnabled.value,
    base_url: customBaseUrl.value.trim(),
    model: customModel.value.trim(),
  }
  if (customApiKey.value.trim()) {
    config.api_key = customApiKey.value.trim()
  }
  emit('setCustom', config)
}

function handleToggleCustom() {
  emit('setCustom', { enabled: customEnabled.value })
}
</script>

<template>
  <div class="embedding-settings">
    <h2 class="section-title">向量模型</h2>
    <p class="section-desc">
      用于知识库文档的向量化。可选择指定模型、自定义独立配置、或留空自动推断。
    </p>

    <!-- 当前状态 -->
    <el-card shadow="never" class="settings-card">
      <template #header><span class="card-header-text">当前模型</span></template>
      <div class="current-model">
        <el-icon class="model-icon"><Coin /></el-icon>
        <span class="model-name">{{ currentDisplay }}</span>
      </div>
    </el-card>

    <!-- 自定义向量模型 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span>自定义向量模型</span>
          <el-switch
            v-model="customEnabled"
            :loading="saving"
            @change="handleToggleCustom"
          />
        </div>
      </template>
      <p class="sub-desc">
        独立配置 base_url / api_key / model，与厂商设置解耦。启用后优先级最高。
      </p>
      <el-form label-width="80px" label-position="right" :disabled="!customEnabled">
        <el-form-item label="Base URL">
          <el-input
            v-model="customBaseUrl"
            placeholder="如 https://api.openai.com/v1"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="customApiKey"
            type="password"
            show-password
            placeholder="输入 API Key"
          />
        </el-form-item>
        <el-form-item label="模型 ID">
          <el-input
            v-model="customModel"
            placeholder="如 text-embedding-3-small, embedding-3, bge-large-zh"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" :disabled="!customEnabled" @click="handleSaveCustom">
            保存配置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 从厂商选择 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span>从厂商模型列表选择</span>
        </div>
      </template>

      <el-radio-group v-model="selectedRef" class="model-radio-group">
        <el-radio value="" class="model-radio">
          <div class="model-option">
            <span class="model-label">自动推断</span>
            <span class="model-desc">系统从已配置 API Key 的厂商中自动查找 embedding 模型</span>
          </div>
        </el-radio>

        <el-radio
          v-for="m in config?.available_models || []"
          :key="m.ref"
          :value="m.ref"
          class="model-radio"
        >
          <div class="model-option">
            <span class="model-label">{{ m.model }}</span>
            <span class="model-provider">{{ m.provider_name }}</span>
            <el-tag v-if="!m.has_api_key" size="small" type="danger">未填 Key</el-tag>
            <el-tag v-else size="small" type="success">可用</el-tag>
          </div>
        </el-radio>
      </el-radio-group>

      <div v-if="!hasAvailable" class="empty-state">
        暂未发现 embedding 模型。请先为厂商拉取模型列表（模型名含 embedding/bge/e5/gte 关键词）。
      </div>

      <div v-if="noKeyModels.length > 0" class="warning-tip">
        <el-icon><WarningFilled /></el-icon>
        <span>部分模型对应的厂商未填写 API Key，选择后可能无法正常使用。</span>
      </div>

      <div class="action-row">
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!config || selectedRef === (config.embedding_model || '')"
          @click="handleSave"
        >
          保存设置
        </el-button>
        <el-button
          v-if="config && config.embedding_model"
          :loading="saving"
          @click="handleClear"
        >
          切换为自动推断
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0 0 4px; }
.section-desc { font-size: 13px; color: #909399; margin: 0 0 20px; }
.sub-desc { font-size: 12px; color: #909399; margin: 0 0 16px; }
.settings-card { margin-bottom: 16px; border-radius: 12px; border: 1px solid #ebeef5; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 500; gap: 8px; }
.card-header-text { font-size: 15px; font-weight: 500; }

.current-model {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
}
.model-icon { color: #409eff; font-size: 18px; }
.model-name { font-weight: 500; color: #303133; }

.model-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.model-radio {
  width: 100%;
  height: auto !important;
  margin-right: 0 !important;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  transition: border-color 0.2s;
}
.model-radio:hover { border-color: #c6e2ff; }
.model-radio.is-checked { border-color: #409eff; background: #ecf5ff; }

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.model-label { font-weight: 500; font-family: monospace; font-size: 14px; }
.model-desc { font-size: 12px; color: #909399; }
.model-provider { font-size: 12px; color: #909399; }

.empty-state {
  text-align: center;
  padding: 32px;
  color: #c0c4cc;
  font-size: 14px;
}

.warning-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-radius: 6px;
  font-size: 12px;
  color: #e6a23c;
}

.action-row {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>
