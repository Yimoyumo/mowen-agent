import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { KnowledgeBase } from '@/types/api'

const KB_STORAGE_KEY = 'mowen-current-kb-id'

function loadCurrentKbId(): string | null {
  try {
    return localStorage.getItem(KB_STORAGE_KEY)
  } catch {
    return null
  }
}

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const currentKbId = ref<string | null>(loadCurrentKbId())
  const loading = ref(false)

  const currentKb = computed(() =>
    knowledgeBases.value.find((kb) => kb.id === currentKbId.value) ?? null,
  )

  // 自动持久化当前选中的知识库 ID
  watch(currentKbId, (val) => {
    try {
      if (val) {
        localStorage.setItem(KB_STORAGE_KEY, val)
      } else {
        localStorage.removeItem(KB_STORAGE_KEY)
      }
    } catch {
      // 静默忽略
    }
  })

  function setKnowledgeBases(list: KnowledgeBase[]) {
    knowledgeBases.value = list
    // 如果持久化的 kbId 不在列表中，清空
    if (currentKbId.value && !list.find((kb) => kb.id === currentKbId.value)) {
      currentKbId.value = null
    }
    // 不自动选择第一个，由用户主动选择
  }

  function addKnowledgeBase(kb: KnowledgeBase) {
    knowledgeBases.value.unshift(kb)
  }

  function removeKnowledgeBase(kbId: string) {
    knowledgeBases.value = knowledgeBases.value.filter((kb) => kb.id !== kbId)
    if (currentKbId.value === kbId) {
      currentKbId.value = knowledgeBases.value[0]?.id ?? null
    }
  }

  function setCurrentKbId(kbId: string | null) {
    currentKbId.value = kbId
  }

  function setLoading(value: boolean) {
    loading.value = value
  }

  return {
    knowledgeBases,
    currentKbId,
    currentKb,
    loading,
    setKnowledgeBases,
    addKnowledgeBase,
    removeKnowledgeBase,
    setCurrentKbId,
    setLoading,
  }
})
