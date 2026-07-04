import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { KnowledgeBase } from '@/types/api'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const currentKbId = ref<string | null>(null)
  const loading = ref(false)

  const currentKb = computed(() =>
    knowledgeBases.value.find((kb) => kb.id === currentKbId.value) ?? null,
  )

  function setKnowledgeBases(list: KnowledgeBase[]) {
    knowledgeBases.value = list
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
