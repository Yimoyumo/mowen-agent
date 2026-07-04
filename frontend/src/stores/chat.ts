import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { AskResponse } from '@/types/api'

export const useChatStore = defineStore('chat', () => {
  const history = ref<AskResponse[]>([])
  const currentResult = ref<AskResponse | null>(null)

  const hasHistory = computed(() => history.value.length > 0)

  function addResult(result: AskResponse) {
    currentResult.value = result
    history.value.unshift(result)
  }

  function setCurrentResult(result: AskResponse | null) {
    currentResult.value = result
  }

  function clearHistory() {
    history.value = []
    currentResult.value = null
  }

  return {
    history,
    currentResult,
    hasHistory,
    addResult,
    setCurrentResult,
    clearHistory,
  }
})
