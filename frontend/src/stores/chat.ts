import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ChatMessage, Conversation } from '@/types/api'
import * as convApi from '@/api/conversations'
import { callWithRetry } from '@/utils/retry'

const STORAGE_KEY = 'mowen-conversations'
const CURRENT_KEY = 'mowen-current-conversation-id'
const SYNCED_KEY = 'mowen-conversations-synced'  // 标记是否已完成后端同步
const LAST_SYNC_KEY = 'mowen-conversations-last-sync'  // 上次增量同步时间戳
const TRIMMED_KEY = 'mowen-conversations-trimmed'  // 被裁剪的会话 ID 列表

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

/** localStorage 容量上限估算（5MB 安全阈值，JSON 字符串长度） */
const LS_SOFT_LIMIT = 4_000_000
/** 裁剪后保留的会话数和消息数 */
const LS_MAX_CONVS = 50
const LS_MAX_MSGS = 200

function saveConversations(conversations: Conversation[]) {
  try {
    // 优先全量保存，只有超限时才裁剪
    const fullJson = JSON.stringify(conversations)
    if (fullJson.length <= LS_SOFT_LIMIT) {
      localStorage.setItem(STORAGE_KEY, fullJson)
      localStorage.removeItem(TRIMMED_KEY)  // 清除裁剪标记
      return
    }

    // 超限：裁剪最近 N 个会话，每个会话保留最近 N 条消息
    const trimmed = conversations
      .slice(0, LS_MAX_CONVS)
      .map(c => ({
        ...c,
        messages: c.messages.slice(-LS_MAX_MSGS),
      }))
    const trimmedJson = JSON.stringify(trimmed)
    localStorage.setItem(STORAGE_KEY, trimmedJson)

    // 记录被裁剪的会话 ID 列表，启动同步时从后端恢复
    const trimmedIds = conversations.slice(LS_MAX_CONVS).map(c => c.id)
    if (trimmedIds.length > 0) {
      localStorage.setItem(TRIMMED_KEY, JSON.stringify(trimmedIds))
      console.warn(`[chat] localStorage 已裁剪，${trimmedIds.length} 个旧会话仅后端保留`)
    } else {
      localStorage.removeItem(TRIMMED_KEY)
    }
  } catch {
    // 存储满或不可用时静默忽略（Pinia 内存仍有全量数据）
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

  // ==================== 多 Tab 同步 ====================

  // BroadcastChannel：跨 Tab 通知数据变更
  // 消息格式：{ type: 'updated' | 'deleted' | 'cleared', convId?: string }
  const channel: BroadcastChannel | null = (() => {
    try {
      return new BroadcastChannel('mowen-conversations-sync')
    } catch {
      return null  // 老浏览器不支持，降级为无同步
    }
  })()

  /** 本 Tab 是否正在应用来自其他 Tab 的变更（避免广播循环） */
  let applyingRemoteChange = false

  if (channel) {
    channel.onmessage = async (event) => {
      const data = event.data as { type: string; convId?: string }
      if (!data || !data.type) return

      // 防止本 Tab 自己发的消息回环
      if (applyingRemoteChange) return
      applyingRemoteChange = true
      try {
        if (data.type === 'cleared') {
          // 其他 Tab 清空了，本 Tab 也清空（不广播、不删除后端）
          conversations.value = []
          currentId.value = null
          localStorage.removeItem(STORAGE_KEY)
          localStorage.removeItem(CURRENT_KEY)
        } else if (data.type === 'deleted' && data.convId) {
          // 其他 Tab 删除了某会话
          const idx = conversations.value.findIndex(c => c.id === data.convId)
          if (idx !== -1) {
            conversations.value.splice(idx, 1)
            if (currentId.value === data.convId) {
              currentId.value = conversations.value[0]?.id ?? null
            }
          }
        } else if (data.type === 'updated' && data.convId) {
          // 其他 Tab 增/改了某会话，从后端拉取最新状态
          const remote = await convApi.getConversation(data.convId).catch(() => null)
          if (!remote) return
          const idx = conversations.value.findIndex(c => c.id === data.convId)
          if (idx === -1) {
            // 本地没有 -> 前插
            conversations.value.unshift(remote)
          } else {
            // 本地已有 -> 覆盖（以后端为准，其他 Tab 可能已更新）
            // 但如果本地正在流式输出该会话，跳过覆盖避免打断
            const local = conversations.value[idx]
            const isStreaming = local.messages.some(m =>
              m.segments?.some(s => s.type === 'tool' && s.status === 'running')
            )
            if (!isStreaming) {
              conversations.value[idx] = remote
            }
          }
        }
      } finally {
        applyingRemoteChange = false
      }
    }
  }

  /** 广播变更到其他 Tab（在 applyRemoteChange=false 时才发，避免循环） */
  function broadcast(type: 'updated' | 'deleted' | 'cleared', convId?: string) {
    if (!channel || applyingRemoteChange) return
    try {
      channel.postMessage({ type, convId })
    } catch {
      // 静默忽略
    }
  }

  // ==================== 后端同步 ====================

  /** 从后端加载所有会话，合并到本地。
   *  - 首次：全量上传 localStorage + 全量拉取后端
   *  - 后续：增量拉取（只拉 updatedAt > lastSyncAt 的会话），减少 N+1
   */
  async function syncFromBackend() {
    if (syncing.value) return
    syncing.value = true
    try {
      const lastSyncAt = Number(localStorage.getItem(LAST_SYNC_KEY) || '0')

      // 首次同步：把 localStorage 的数据上传到后端
      if (!backendSynced.value && conversations.value.length > 0) {
        await convApi.syncConversations(conversations.value)
        localStorage.setItem(SYNCED_KEY, '1')
        backendSynced.value = true
      }

      // 从后端拉取会话列表（增量：只拉 updatedAt > lastSyncAt 的）
      const backendConvs = await convApi.listConversations(lastSyncAt)

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
      // 记录本次同步时间（用于下次增量）
      localStorage.setItem(LAST_SYNC_KEY, String(Date.now()))    } catch (e) {
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

    // 后端持久化（带重试，失败 toast 提示）
    callWithRetry(() => convApi.createConversation({
      id: conv.id, title: conv.title, kbId: conv.kbId,
      createdAt: conv.createdAt, updatedAt: conv.updatedAt,
    })).then(() => broadcast('updated', conv.id))

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

    // 后端删除（带重试）
    callWithRetry(() => convApi.deleteConversation(id)).then(() => broadcast('deleted', id))
  }

  async function clearAllConversations() {
    conversations.value = []
    currentId.value = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(CURRENT_KEY)
    localStorage.removeItem(TRIMMED_KEY)
    localStorage.removeItem(LAST_SYNC_KEY)

    // 后端清空（带重试）
    callWithRetry(() => convApi.deleteAllConversations()).then(() => broadcast('cleared'))
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
      callWithRetry(() => convApi.updateConversation(convId, { title: conv.title }), true)
        .then(() => broadcast('updated', convId))
    }

    // 后端持久化（带重试）
    callWithRetry(() => convApi.addMessage(convId, msg))
      .then(() => broadcast('updated', convId))

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
    callWithRetry(() => convApi.updateConversation(convId, { kbId }))
      .then(() => broadcast('updated', convId))
  }

  /** 确保有当前会话，没有则创建 */
  function ensureCurrentConversation(): Conversation {
    if (currentConversation.value) return currentConversation.value
    return createConversation()
  }

  /** 暴露广播函数，供流式结束同步成功后触发跨 Tab 通知 */
  function broadcastChange(type: 'updated' | 'deleted' | 'cleared', convId?: string) {
    broadcast(type, convId)
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
    broadcastChange,
  }
})
