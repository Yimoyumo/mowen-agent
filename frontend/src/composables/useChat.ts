import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { chatStream } from '@/api/chat'
import { apiClient } from '@/api/config'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import type { ChatMessage } from '@/types/api'

function loadBool(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v !== null ? v === 'true' : fallback
  } catch { return fallback }
}

function saveBool(key: string, value: boolean) {
  try { localStorage.setItem(key, String(value)) } catch { /* ignore */ }
}

export function useChat() {
  const store = useChatStore()
  const kbStore = useKnowledgeBaseStore()

  const question = ref('')
  const loading = ref(false)
  const streaming = ref(false)
  const abortFn = ref<(() => void) | null>(null)

  // 用户可切换的运行时选项（localStorage 持久化）
  const streamEnabled = ref(loadBool('mowen-stream', true))
  const showReasoning = ref(loadBool('mowen-reasoning', false))

  // 本次对话的 token 统计
  const tokenStats = ref<{ input_tokens: number; output_tokens: number; context_window: number } | null>(null)

  watch(streamEnabled, v => saveBool('mowen-stream', v))
  watch(showReasoning, v => saveBool('mowen-reasoning', v))

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

  async function sendMessage(text?: string, uploadedFiles?: { token: string; filename: string }[]) {
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

    // 添加 assistant 占位消息（带空 segments）
    const assistantMsg = store.addMessage(conv.id, {
      role: 'assistant',
      content: '',
      contexts: [],
      segments: [],
    })

    // 构建请求消息（包含刚添加的用户消息，不含占位的空 assistant）
    const apiMessages = buildApiMessages()

    let abortCalled = false

    abortFn.value = chatStream(
      apiMessages,
      kbStore.currentKbId,
      {
        onContexts: (contexts) => {
          store.updateMessage(conv.id, assistantMsg.id, { contexts })
        },
        onReasoning: (token) => {
          const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
          if (msg) {
            store.updateMessage(conv.id, assistantMsg.id, {
              reasoning: (msg.reasoning ?? '') + token,
            })
          }
        },
        onTokenStats: (stats) => {
          tokenStats.value = stats
        },
        onToolStart: (tool, input) => {
          const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
          if (msg) {
            const segs = [...(msg.segments ?? [])]
            // 推入一个新的 tool segment
            segs.push({ type: 'tool', tool, input, status: 'running' })
            store.updateMessage(conv.id, assistantMsg.id, { segments: segs })
          }
        },
        onToolEnd: (tool, output) => {
          const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
          if (msg) {
            const segs = [...(msg.segments ?? [])]
            // 从后往前找第一个同名且 running 的 tool segment
            for (let i = segs.length - 1; i >= 0; i--) {
              const seg = segs[i]
              if (seg && seg.type === 'tool' && seg.tool === tool && seg.status === 'running') {
                segs[i] = { ...seg, type: 'tool', tool, output, status: 'done' }
                break
              }
            }
            store.updateMessage(conv.id, assistantMsg.id, { segments: segs })
          }
        },
        onToken: (token) => {
          const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
          if (msg) {
            // 追加到 content（向后兼容）
            const newContent = msg.content + token
            // 同步更新 segments：追加到最后一个 text segment，或创建新的
            const segs = [...(msg.segments ?? [])]
            const last = segs[segs.length - 1]
            if (last && last.type === 'text') {
              segs[segs.length - 1] = { type: 'text', content: last.content + token }
            } else {
              segs.push({ type: 'text', content: token })
            }
            store.updateMessage(conv.id, assistantMsg.id, { content: newContent, segments: segs })
          }
        },
        onDone: (stats) => {
          loading.value = false
          streaming.value = false
          abortFn.value = null
          if (stats) tokenStats.value = stats
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
      },
      {
        stream: streamEnabled.value,
        showReasoning: showReasoning.value,
        uploadedFiles: uploadedFiles ?? undefined,
        sessionId: conv.id,
      },
    )

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

  async function destroySandbox(sessionId: string) {
    try {
      await fetch(`${apiClient.defaults.baseURL}/sandbox/destroy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      })
    } catch { /* 静默 */ }
  }

  async function selectConversation(id: string) {
    // 切换会话前，销毁当前会话的沙盒
    const current = store.currentConversation
    if (current && current.id !== id) {
      destroySandbox(current.id)
    }
    store.selectConversation(id)
  }

  async function deleteConversation(id: string) {
    // 删除会话时同时销毁沙盒
    destroySandbox(id)
    store.deleteConversation(id)
  }

  function createNewConversation() {
    store.createConversation()
  }

  async function clearAllConversations() {
    // 清空时销毁所有会话的沙盒
    for (const conv of store.conversations) {
      destroySandbox(conv.id)
    }
    store.clearAllConversations()
  }

  function setQuestion(value: string) {
    question.value = value
  }

  return {
    question,
    loading,
    streaming,
    streamEnabled,
    showReasoning,
    tokenStats,
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
