import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { chatStream } from '@/api/chat'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import type { ChatMessage } from '@/types/api'

export function useChat() {
  const store = useChatStore()
  const kbStore = useKnowledgeBaseStore()

  const question = ref('')
  const loading = ref(false)
  const streaming = ref(false)
  const abortFn = ref<(() => void) | null>(null)

  const currentConversation = computed(() => store.currentConversation)
  const messages = computed(() => store.currentMessages)

  /** 构建 API 请求所需的消息格式（过滤掉空的正在生成的 assistant 消息） */
  function buildApiMessages(): { role: 'user' | 'assistant'; content: string }[] {
    const conv = store.currentConversation
    if (!conv) return []
    // 取最近 20 条消息作为上下文
    return conv.messages
      .slice(-20)
      .filter(m => m.content.trim().length > 0)
      .map(m => ({
        role: m.role,
        content: m.content,
      }))
  }

  async function sendMessage(text?: string) {
    const q = (text ?? question.value).trim()
    if (!q) {
      ElMessage.warning('请输入问题')
      return
    }
    if (loading.value) return

    // 确保有当前会话
    const conv = store.ensureCurrentConversation()

    // 同步会话的 KB 设置
    store.setConversationKb(conv.id, kbStore.currentKbId)

    // 添加用户消息
    store.addMessage(conv.id, { role: 'user', content: q })

    loading.value = true
    streaming.value = true
    question.value = ''

    // 添加 assistant 占位消息
    const assistantMsg = store.addMessage(conv.id, {
      role: 'assistant',
      content: '',
      contexts: [],
    })

    // 构建请求消息（包含刚添加的用户消息，不含占位的空 assistant）
    const apiMessages = buildApiMessages()

    let abortCalled = false

    abortFn.value = chatStream(apiMessages, kbStore.currentKbId, {
      onContexts: (contexts) => {
        store.updateMessage(conv.id, assistantMsg.id, { contexts })
      },
      onToken: (token) => {
        const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
        if (msg) {
          store.updateMessage(conv.id, assistantMsg.id, { content: msg.content + token })
        }
      },
      onDone: () => {
        loading.value = false
        streaming.value = false
        abortFn.value = null
      },
      onError: (msg) => {
        if (abortCalled) return
        loading.value = false
        streaming.value = false
        abortFn.value = null
        const current = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
        const errorMsg = `\n\n[生成失败] ${msg}`
        store.updateMessage(conv.id, assistantMsg.id, {
          content: (current?.content ?? '') + errorMsg,
        })
        ElMessage.error(msg)
      },
    })

    // 保存 abort 函数用于外部中断
    return () => {
      abortCalled = true
      abortFn.value?.()
      abortFn.value = null
      loading.value = false
      streaming.value = false
    }
  }

  function stopStreaming() {
    if (abortFn.value) {
      abortFn.value()
      abortFn.value = null
      loading.value = false
      streaming.value = false
    }
  }

  function selectConversation(id: string) {
    store.selectConversation(id)
  }

  function deleteConversation(id: string) {
    store.deleteConversation(id)
  }

  function createNewConversation() {
    store.createConversation()
  }

  function clearAllConversations() {
    store.clearAllConversations()
  }

  function setQuestion(value: string) {
    question.value = value
  }

  return {
    question,
    loading,
    streaming,
    messages,
    currentConversation,
    conversations: computed(() => store.conversations),
    sendMessage,
    stopStreaming,
    selectConversation,
    deleteConversation,
    createNewConversation,
    clearAllConversations,
    setQuestion,
  }
}
