import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'
import { askQuestion } from '@/api/chat'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import type { AskResponse } from '@/types/api'

export function useChat() {
  const store = useChatStore()
  const kbStore = useKnowledgeBaseStore()

  const question = ref('')
  const loading = ref(false)
  const streaming = ref(false)
  const currentResult = computed(() => store.currentResult)

  async function sendQuestion(text?: string) {
    const q = (text ?? question.value).trim()
    if (!q) {
      ElMessage.warning('请输入问题')
      return
    }

    loading.value = true
    streaming.value = true
    const draft: AskResponse = {
      question: q,
      answer: '',
      contexts: [],
    }
    store.addResult(draft)

    try {
      const result = await askQuestion(q, kbStore.currentKbId ?? undefined)
      draft.question = result.question
      draft.contexts = result.contexts
      draft.answer = result.answer
      question.value = ''
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      draft.answer += `\n\n[生成失败] ${axiosErr.response?.data?.detail || '问答请求失败'}`
      ElMessage.error(axiosErr.response?.data?.detail || '问答请求失败')
    } finally {
      loading.value = false
      streaming.value = false
    }
  }

  function selectHistory(item: AskResponse) {
    store.setCurrentResult(item)
  }

  function setQuestion(value: string) {
    question.value = value
  }

  return {
    question,
    loading,
    streaming,
    currentResult,
    history: computed(() => store.history),
    sendQuestion,
    selectHistory,
    setQuestion,
  }
}
