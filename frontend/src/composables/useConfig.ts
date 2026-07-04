import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfig } from '@/api/chat'
import type { ConfigResponse } from '@/types/api'

export function useConfig() {
  const config = ref<ConfigResponse | null>(null)
  const isReady = computed(() => config.value !== null)

  onMounted(async () => {
    try {
      config.value = await getConfig()
    } catch {
      ElMessage.error('连接后端失败，请确认 API 服务已启动')
    }
  })

  return { config, isReady }
}
