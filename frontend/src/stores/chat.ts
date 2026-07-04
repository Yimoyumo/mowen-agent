import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ChatMessage, Conversation } from '@/types/api'

const STORAGE_KEY = 'mowen-conversations'
const CURRENT_KEY = 'mowen-current-conversation-id'

function genId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadCurrentId(): string | null {
  try {
    return localStorage.getItem(CURRENT_KEY)
  } catch {
    return null
  }
}

function saveConversations(conversations: Conversation[]) {
  try {
    // 只保留最近 30 个会话，每个会话最多 100 条消息
    const trimmed = conversations
      .slice(0, 30)
      .map(c => ({
        ...c,
        messages: c.messages.slice(-100),
      }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  } catch {
    // 存储满或不可用时静默忽略
  }
}

function saveCurrentId(id: string | null) {
  try {
    if (id) {
      localStorage.setItem(CURRENT_KEY, id)
    } else {
      localStorage.removeItem(CURRENT_KEY)
    }
  } catch {
    // 静默忽略
  }
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>(loadConversations())
  const currentId = ref<string | null>(loadCurrentId())

  const currentConversation = computed(() =>
    conversations.value.find(c => c.id === currentId.value) ?? null,
  )

  const currentMessages = computed(() =>
    currentConversation.value?.messages ?? [],
  )

  const hasConversations = computed(() => conversations.value.length > 0)

  // 自动持久化
  watch(conversations, (val) => saveConversations(val), { deep: true })
  watch(currentId, (val) => saveCurrentId(val))

  function createConversation(title: string = '新对话'): Conversation {
    const now = Date.now()
    const conv: Conversation = {
      id: genId(),
      title,
      messages: [],
      kbId: null,
      createdAt: now,
      updatedAt: now,
    }
    conversations.value.unshift(conv)
    currentId.value = conv.id
    return conv
  }

  function selectConversation(id: string) {
    currentId.value = id
  }

  function deleteConversation(id: string) {
    const idx = conversations.value.findIndex(c => c.id === id)
    if (idx === -1) return
    conversations.value.splice(idx, 1)
    if (currentId.value === id) {
      currentId.value = conversations.value[0]?.id ?? null
    }
  }

  function clearAllConversations() {
    conversations.value = []
    currentId.value = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(CURRENT_KEY)
  }

  function addMessage(convId: string, message: Omit<ChatMessage, 'id' | 'createdAt'>): ChatMessage {
    const conv = conversations.value.find(c => c.id === convId)
    if (!conv) throw new Error('会话不存在')

    const msg: ChatMessage = {
      ...message,
      id: genId(),
      createdAt: Date.now(),
    }
    conv.messages.push(msg)
    conv.updatedAt = Date.now()

    // 如果是第一条用户消息，更新会话标题
    if (message.role === 'user' && conv.messages.length === 1) {
      conv.title = message.content.slice(0, 30) || '新对话'
    }

    return msg
  }

  function updateMessage(convId: string, msgId: string, updates: Partial<ChatMessage>) {
    const conv = conversations.value.find(c => c.id === convId)
    if (!conv) return
    const msg = conv.messages.find(m => m.id === msgId)
    if (!msg) return
    Object.assign(msg, updates)
    conv.updatedAt = Date.now()
  }

  function setConversationKb(convId: string, kbId: string | null) {
    const conv = conversations.value.find(c => c.id === convId)
    if (!conv) return
    conv.kbId = kbId
    conv.updatedAt = Date.now()
  }

  /** 确保有当前会话，没有则创建 */
  function ensureCurrentConversation(): Conversation {
    if (currentConversation.value) return currentConversation.value
    return createConversation()
  }

  return {
    conversations,
    currentId,
    currentConversation,
    currentMessages,
    hasConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    clearAllConversations,
    addMessage,
    updateMessage,
    setConversationKb,
    ensureCurrentConversation,
  }
})
