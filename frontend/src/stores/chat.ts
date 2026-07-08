import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ChatMessage, Conversation } from '@/types/api'
import * as convApi from '@/api/conversations'

const STORAGE_KEY = 'mowen-conversations'
const CURRENT_KEY = 'mowen-current-conversation-id'
const SYNCED_KEY = 'mowen-conversations-synced'  // 标记是否已完成后端同步

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
    // 只保留最近 50 个会话，每个会话最多 200 条消息
    const trimmed = conversations
      .slice(0, 50)
      .map(c => ({
        ...c,
        messages: c.messages.slice(-200),
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
  const syncing = ref(false)  // 是否正在从后端同步
  const backendSynced = ref(localStorage.getItem(SYNCED_KEY) === '1')

  const currentConversation = computed(() =>
    conversations.value.find(c => c.id === currentId.value) ?? null,
  )

  const currentMessages = computed(() =>
    currentConversation.value?.messages ?? [],
  )

  const hasConversations = computed(() => conversations.value.length > 0)

  // localStorage 自动持久化（降级备用）
  watch(conversations, (val) => saveConversations(val), { deep: true })
  watch(currentId, (val) => saveCurrentId(val))

  // ==================== 后端同步 ====================

  /** 从后端加载所有会话，合并到本地 */
  async function syncFromBackend() {
    if (syncing.value) return
    syncing.value = true
    try {
      // 首次同步：把 localStorage 的数据上传到后端
      if (!backendSynced.value && conversations.value.length > 0) {
        await convApi.syncConversations(conversations.value)
        localStorage.setItem(SYNCED_KEY, '1')
        backendSynced.value = true
      }

      // 从后端拉取会话列表
      const backendConvs = await convApi.listConversations()

      // 合并：后端有的本地没有 → 从后端拉取完整会话
      //       本地有后端没有 → 上传到后端
      const backendIds = new Set(backendConvs.map(c => c.id))
      const localIds = new Set(conversations.value.map(c => c.id))

      // 后端有但本地没有的 → 拉取完整数据
      for (const bc of backendConvs) {
        if (!localIds.has(bc.id)) {
          const full = await convApi.getConversation(bc.id)
          if (full) {
            conversations.value.unshift(full)
          }
        } else {
          // 更新本地会话的标题等元数据
          const local = conversations.value.find(c => c.id === bc.id)
          if (local) {
            local.title = bc.title
            local.kbId = bc.kbId
            local.updatedAt = bc.updatedAt
          }
        }
      }

      // 本地有但后端没有的 → 上传
      for (const lc of conversations.value) {
        if (!backendIds.has(lc.id)) {
          await convApi.createConversation({
            id: lc.id, title: lc.title, kbId: lc.kbId,
            createdAt: lc.createdAt, updatedAt: lc.updatedAt,
          })
          for (const msg of lc.messages) {
            await convApi.addMessage(lc.id, msg)
          }
        }
      }
    } catch (e) {
      // 后端不可用时静默降级到 localStorage
      console.warn('后端同步失败，降级到 localStorage:', e)
    } finally {
      syncing.value = false
    }
  }

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

    // 后端持久化（不阻塞，失败静默）
    convApi.createConversation({
      id: conv.id, title: conv.title, kbId: conv.kbId,
      createdAt: conv.createdAt, updatedAt: conv.updatedAt,
    }).catch(() => {})

    return conv
  }

  function selectConversation(id: string) {
    currentId.value = id
  }

  async function deleteConversation(id: string) {
    const idx = conversations.value.findIndex(c => c.id === id)
    if (idx === -1) return
    conversations.value.splice(idx, 1)
    if (currentId.value === id) {
      currentId.value = conversations.value[0]?.id ?? null
    }

    // 后端删除（不阻塞）
    convApi.deleteConversation(id).catch(() => {})
  }

  async function clearAllConversations() {
    conversations.value = []
    currentId.value = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(CURRENT_KEY)

    // 后端清空
    convApi.deleteAllConversations().catch(() => {})
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
      convApi.updateConversation(convId, { title: conv.title }).catch(() => {})
    }

    // 后端持久化（不阻塞）
    convApi.addMessage(convId, msg).catch(() => {})

    return msg
  }

  function updateMessage(convId: string, msgId: string, updates: Partial<ChatMessage>) {
    const conv = conversations.value.find(c => c.id === convId)
    if (!conv) return
    const msg = conv.messages.find(m => m.id === msgId)
    if (!msg) return
    Object.assign(msg, updates)
    conv.updatedAt = Date.now()
    // 不在此处同步后端：流式输出时每个 token 都触发更新，
    // 后端尚未完成 addMessage → 大量 404。统一在 onDone 时同步。
  }

  function setConversationKb(convId: string, kbId: string | null) {
    const conv = conversations.value.find(c => c.id === convId)
    if (!conv) return
    conv.kbId = kbId
    conv.updatedAt = Date.now()

    // 后端持久化
    convApi.updateConversation(convId, { kbId }).catch(() => {})
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
    syncing,
    syncFromBackend,
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
