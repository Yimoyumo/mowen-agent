import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { AskResponse } from '@/types/api'

const STORAGE_KEY = 'mowen-chat-history'

function loadHistory(): AskResponse[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveHistory(history: AskResponse[]) {
  try {
    // 只保留最近 50 条，避免超出 localStorage 容量
    const trimmed = history.slice(0, 50)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  } catch {
    // 存储满或不可用时静默忽略
  }
}

export const useChatStore = defineStore('chat', () => {
  const history = ref<AskResponse[]>(loadHistory())
  const currentResult = ref<AskResponse | null>(null)

  const hasHistory = computed(() => history.value.length > 0)

  // 自动持久化
  watch(
    history,
    (val) => saveHistory(val),
    { deep: true },
  )

  function addResult(result: AskResponse) {
    currentResult.value = result
    history.value.unshift(result)
  }

  function setCurrentResult(result: AskResponse | null) {
    currentResult.value = result
  }

  function removeHistory(index: number) {
    const removed = history.value[index]
    history.value.splice(index, 1)
    if (currentResult.value === removed) {
      currentResult.value = null
    }
  }

  function clearHistory() {
    history.value = []
    currentResult.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  return {
    history,
    currentResult,
    hasHistory,
    addResult,
    setCurrentResult,
    removeHistory,
    clearHistory,
  }
})
