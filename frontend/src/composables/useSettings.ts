/** 用户设置 composable */

import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getSettings,
  updateSettings,
  resetSettings,
  getProviders,
  updateProvider,
  addCustomProvider,
  deleteCustomProvider,
  fetchProviderModels,
  setCurrentModel,
  getProfile,
  updateProfile,
  getMemories,
  addMemory,
  updateMemory,
  deleteMemory,
  clearMemories,
  getEmbeddingConfig,
  setEmbeddingModel,
  setEmbeddingCustom,
} from '@/api/settingsApi'
import type {
  UserSettings,
  ProvidersResponse,
  ProviderInfo,
  UserProfile,
  MemoryItem,
  EmbeddingConfig,
} from '@/types/api'

export function useSettings() {
  const settings = ref<UserSettings | null>(null)
  const providers = ref<ProvidersResponse | null>(null)
  const profile = ref<UserProfile | null>(null)
  const memories = ref<MemoryItem[]>([])
  const embeddingConfig = ref<EmbeddingConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const fetching = ref(false)   // 正在拉取模型列表

  async function loadAll() {
    loading.value = true
    try {
      const [s, p, prof, mem, embed] = await Promise.all([
        getSettings(),
        getProviders(),
        getProfile(),
        getMemories(),
        getEmbeddingConfig(),
      ])
      settings.value = s
      providers.value = p
      profile.value = prof
      memories.value = mem.memories
      embeddingConfig.value = embed
    } catch {
      ElMessage.error('加载设置失败')
    } finally {
      loading.value = false
    }
  }

  async function loadSettings() {
    try {
      settings.value = await getSettings()
    } catch {
      ElMessage.error('加载设置失败')
    }
  }

  async function loadProviders() {
    try {
      providers.value = await getProviders()
    } catch {
      ElMessage.error('加载厂商列表失败')
    }
  }

  async function handleSetEmbeddingModel(modelRef: string) {
    saving.value = true
    try {
      await setEmbeddingModel(modelRef)
      embeddingConfig.value = await getEmbeddingConfig()
      ElMessage.success(modelRef ? '向量模型已设置' : '已切换为自动推断')
    } catch {
      ElMessage.error('设置失败')
    } finally {
      saving.value = false
    }
  }

  async function handleSetEmbeddingCustom(config: {
    enabled?: boolean
    base_url?: string
    api_key?: string
    model?: string
  }) {
    saving.value = true
    try {
      await setEmbeddingCustom(config)
      embeddingConfig.value = await getEmbeddingConfig()
      ElMessage.success('自定义向量模型配置已保存')
    } catch {
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  }

  async function loadMemories() {
    try {
      const res = await getMemories()
      memories.value = res.memories
    } catch {
      ElMessage.error('加载记忆失败')
    }
  }

  async function saveSettings(updates: Partial<UserSettings>) {
    saving.value = true
    try {
      const updated = await updateSettings(updates)
      settings.value = updated
      ElMessage.success('设置已保存')
    } catch {
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  }

  // ---- 厂商管理 ----

  async function handleSaveProviderKey(providerId: string, apiKey: string) {
    saving.value = true
    try {
      await updateProvider(providerId, apiKey)
      await loadProviders()
      ElMessage.success('API Key 已保存')
    } catch {
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  }

  async function handleFetchModels(providerId: string): Promise<string[]> {
    fetching.value = true
    try {
      const result = await fetchProviderModels(providerId)
      if (result.models && result.models.length > 0) {
        // 更新本地缓存
        await loadProviders()
        ElMessage.success(`获取到 ${result.models.length} 个模型`)
        return result.models
      }
      ElMessage.warning(result.message || '未能获取模型列表')
      return []
    } catch {
      ElMessage.error('获取模型列表失败')
      return []
    } finally {
      fetching.value = false
    }
  }

  async function handleSelectModel(modelRef: string) {
    saving.value = true
    try {
      await setCurrentModel(modelRef)
      if (providers.value) {
        providers.value.active_model = modelRef
      }
      ElMessage.success('模型已切换')
    } catch {
      ElMessage.error('切换失败')
    } finally {
      saving.value = false
    }
  }

  async function handleAddProvider(name: string, baseUrl: string, apiKey: string): Promise<boolean> {
    try {
      await addCustomProvider(name, baseUrl, apiKey)
      await loadProviders()
      ElMessage.success('自定义厂商已添加')
      return true
    } catch {
      ElMessage.error('添加失败')
      return false
    }
  }

  async function handleDeleteProvider(providerId: string) {
    try {
      await deleteCustomProvider(providerId)
      await loadProviders()
      ElMessage.success('厂商已删除')
    } catch {
      ElMessage.error('删除失败')
    }
  }

  // ---- 用户画像 ----

  async function saveProfile(p: UserProfile) {
    saving.value = true
    try {
      const updated = await updateProfile(p)
      profile.value = updated
      ElMessage.success('用户画像已保存')
    } catch {
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  }

  // ---- 记忆管理 ----

  async function handleAddMemory(type: string, content: string): Promise<boolean> {
    try {
      await addMemory(type, content)
      await loadMemories()
      ElMessage.success('记忆已添加')
      return true
    } catch {
      ElMessage.error('添加失败')
      return false
    }
  }

  async function handleUpdateMemory(id: string, type: string, content: string): Promise<boolean> {
    try {
      await updateMemory(id, type, content)
      await loadMemories()
      ElMessage.success('记忆已更新')
      return true
    } catch {
      ElMessage.error('更新失败')
      return false
    }
  }

  async function handleDeleteMemory(id: string) {
    try {
      await deleteMemory(id)
      memories.value = memories.value.filter((m) => m.id !== id)
      ElMessage.success('记忆已删除')
    } catch {
      ElMessage.error('删除失败')
    }
  }

  async function handleClearMemories() {
    try {
      await clearMemories()
      memories.value = []
      ElMessage.success('所有记忆已清空')
    } catch {
      ElMessage.error('清空失败')
    }
  }

  async function handleReset() {
    try {
      const defaults = await resetSettings()
      settings.value = defaults
      ElMessage.success('设置已重置')
    } catch {
      ElMessage.error('重置失败')
    }
  }

  onMounted(loadAll)

  return {
    settings,
    providers,
    profile,
    memories,
    loading,
    saving,
    fetching,
    embeddingConfig,
    loadAll,
    loadSettings,
    loadProviders,
    loadMemories,
    saveSettings,
    handleSaveProviderKey,
    handleFetchModels,
    handleSelectModel,
    handleAddProvider,
    handleDeleteProvider,
    handleSetEmbeddingModel,
    handleSetEmbeddingCustom,
    saveProfile,
    handleAddMemory,
    handleUpdateMemory,
    handleDeleteMemory,
    handleClearMemories,
    handleReset,
  }
}
