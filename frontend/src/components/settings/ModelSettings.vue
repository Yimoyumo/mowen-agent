<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ProvidersResponse, ProviderInfo } from '@/types/api'
import { testModel } from '@/api/settingsApi'

interface Props {
  providers: ProvidersResponse
  fetching: boolean
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  saveKey: [providerId: string, apiKey: string]
  fetchModels: [providerId: string, callback: (models: string[]) => void]
  addProvider: [name: string, baseUrl: string, apiKey: string, callback: (ok: boolean) => void]
  deleteProvider: [providerId: string]
}>()

const selectedProviderId = ref('')
let _initialized = false

function syncSelected() {
  if (_initialized) return
  const active = props.providers.active_model
  if (active && active.includes('/')) {
    const pid = active.split('/')[0]!
    if (props.providers.providers.some((p) => p.id === pid)) {
      selectedProviderId.value = pid
      _initialized = true
      return
    }
  }
  if (props.providers.providers.length > 0) {
    selectedProviderId.value = props.providers.providers[0]!.id
    _initialized = true
  }
}
watch(() => props.providers, syncSelected, { immediate: true })

const currentProvider = computed(() =>
  props.providers.providers.find((p) => p.id === selectedProviderId.value),
)

const models = ref<string[]>([])
watch(currentProvider, (p) => {
  if (p) models.value = p.models || []
}, { immediate: true })

const apiKey = ref('')

async function handleFetch() {
  const pid = selectedProviderId.value
  if (!pid) return
  emit('fetchModels', pid, (fetchedModels: string[]) => {
    if (fetchedModels.length > 0) models.value = fetchedModels
  })
}

function handleSaveKey() {
  if (!apiKey.value.trim()) { ElMessage.warning('请输入 API Key'); return }
  emit('saveKey', selectedProviderId.value, apiKey.value.trim())
  apiKey.value = ''
}

// ---- 测试联通 ----
const testingModel = ref<string | null>(null)
const testResults = ref<Record<string, { ok: boolean; ms?: number; error?: string }>>({})

async function handleTestModel(modelName: string) {
  const pid = selectedProviderId.value
  if (!pid) return
  testingModel.value = modelName
  try {
    const result = await testModel(pid, modelName)
    testResults.value[modelName] = {
      ok: result.ok,
      ms: result.latency_ms,
      error: result.error,
    }
    if (result.ok) {
      ElMessage.success(`${modelName}: ${result.latency_ms}ms`)
    } else {
      ElMessage.error(`${modelName}: ${result.error}`)
    }
  } catch {
    testResults.value[modelName] = { ok: false, error: '请求失败' }
  } finally {
    testingModel.value = null
  }
}

const showAddDialog = ref(false)
const newName = ref('')
const newBaseUrl = ref('')
const newApiKey = ref('')

function handleAddProvider() {
  if (!newName.value.trim()) { ElMessage.warning('请输入厂商名称'); return }
  if (!newBaseUrl.value.trim()) { ElMessage.warning('请输入 API 地址'); return }
  emit('addProvider', newName.value.trim(), newBaseUrl.value.trim(), newApiKey.value.trim(), (ok) => {
    if (ok) { showAddDialog.value = false; newName.value = ''; newBaseUrl.value = ''; newApiKey.value = '' }
  })
}

async function handleDeleteProvider() {
  if (!currentProvider.value) return
  if (currentProvider.value.preset) { ElMessage.warning('预设厂商不可删除'); return }
  try {
    await ElMessageBox.confirm(`确定要删除厂商「${currentProvider.value.name}」吗？`, '删除确认', { type: 'warning' })
    emit('deleteProvider', currentProvider.value.id)
  } catch { /* cancelled */ }
}

const providerGroups = computed(() => {
  const groups: { label: string; items: ProviderInfo[] }[] = [
    { label: '预设厂商', items: [] as ProviderInfo[] },
    { label: '自定义厂商', items: [] as ProviderInfo[] },
  ]
  for (const p of props.providers.providers) {
    if (p.preset) groups[0]!.items.push(p)
    else groups[1]!.items.push(p)
  }
  return groups.filter((g) => g.items.length > 0)
})
</script>

<template>
  <div class="model-settings">
    <h2 class="section-title">模型配置</h2>
    <p class="section-desc">选择厂商，填 API Key，拉取可用模型。模型切换在聊天框下方。</p>

    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span>选择厂商</span>
          <el-button size="small" type="primary" @click="showAddDialog = true">
            <el-icon><Plus /></el-icon>自定义厂商
          </el-button>
        </div>
      </template>

      <el-select v-model="selectedProviderId" placeholder="选择一个厂商" style="width: 100%" size="large">
        <el-option-group v-for="group in providerGroups" :key="group.label" :label="group.label">
          <el-option v-for="p in group.items" :key="p.id" :label="p.name" :value="p.id">
            <div class="provider-option">
              <span>{{ p.name }}</span>
              <span class="provider-desc">{{ p.desc }}</span>
              <el-tag v-if="!p.preset" size="small" type="warning">自定义</el-tag>
            </div>
          </el-option>
        </el-option-group>
      </el-select>

      <div v-if="currentProvider && !currentProvider.preset" class="delete-row">
        <el-button text type="danger" size="small" @click="handleDeleteProvider">
          <el-icon><Delete /></el-icon>删除此厂商
        </el-button>
      </div>
    </el-card>

    <el-card v-if="currentProvider" shadow="never" class="settings-card">
      <template #header><span class="card-header-text">API Key</span></template>
      <div class="key-row">
        <el-input
          v-model="apiKey" type="password" show-password size="default"
          :placeholder="currentProvider?.has_api_key ? '已保存 (可修改)' : '输入 API Key'"
          @keydown.enter="handleSaveKey"
        >
          <template #prepend><el-icon><Key /></el-icon></template>
        </el-input>
        <el-button type="primary" :loading="saving" @click="handleSaveKey">保存 Key</el-button>
      </div>
    </el-card>

    <el-card v-if="currentProvider" shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span>可用模型 <span v-if="models.length" class="model-count">({{ models.length }})</span></span>
          <el-button size="small" :loading="fetching" :disabled="!currentProvider?.has_api_key" @click="handleFetch">
            <el-icon><Download /></el-icon>拉取模型列表
          </el-button>
        </div>
      </template>
      <div v-if="models.length === 0" class="empty-state">
        <template v-if="fetching"><el-icon class="is-loading"><Loading /></el-icon>正在拉取…</template>
        <template v-else>点击拉取模型列表</template>
      </div>
      <div v-else class="model-tags">
        <div v-for="m in models" :key="m" class="model-tag-row">
          <el-tag size="default" class="model-tag">{{ m }}</el-tag>
          <el-button
            size="small"
            :loading="testingModel === m"
            :type="testResults[m]?.ok ? 'success' : testResults[m] && !testResults[m].ok ? 'danger' : 'default'"
            plain
            @click="handleTestModel(m)"
          >
            <template v-if="testingModel === m">
              测试中…
            </template>
            <template v-else-if="testResults[m]?.ok">
              {{ testResults[m]!.ms }}ms
            </template>
            <template v-else>
              测试
            </template>
          </el-button>
          <span v-if="testResults[m] && !testResults[m].ok" class="test-error">{{ testResults[m]!.error }}</span>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="showAddDialog" title="添加自定义厂商" width="480px">
      <el-form label-width="90px" label-position="right">
        <el-form-item label="厂商名称"><el-input v-model="newName" placeholder="如：本地 Ollama" /></el-form-item>
        <el-form-item label="API 地址"><el-input v-model="newBaseUrl" placeholder="如：https://api.openai.com/v1" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="newApiKey" type="password" show-password placeholder="可选，稍后也可填写" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAddProvider">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.section-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0 0 4px; }
.section-desc { font-size: 13px; color: #909399; margin: 0 0 20px; }
.settings-card { margin-bottom: 16px; border-radius: 12px; border: 1px solid #ebeef5; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 500; gap: 8px; }
.card-header-text { font-size: 15px; font-weight: 500; }
.provider-option { display: flex; align-items: center; gap: 8px; overflow: hidden; }
.provider-option .provider-desc { color: #909399; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.delete-row { margin-top: 8px; text-align: right; }
.key-row { display: flex; gap: 8px; }
.model-count { font-weight: 400; color: #909399; font-size: 13px; }
.empty-state { text-align: center; padding: 32px; color: #c0c4cc; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.model-tags { display: flex; flex-direction: column; gap: 6px; }
.model-tag-row { display: flex; align-items: center; gap: 8px; }
.model-tag { font-family: monospace; }
.test-error { font-size: 12px; color: #f56c6c; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
