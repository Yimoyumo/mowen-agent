import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { chatStream } from '@/api/chat'
import { apiClient } from '@/api/config'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import { callWithRetry } from '@/utils/retry'
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

  /** 构建 API 请求所需的消息格式。
   * 
   * Checkpointer 模式：后端通过 thread_id 自动恢复历史，前端只需传最新一条消息。
   * 为兼容性仍传完整列表，后端 Checkpointer 会自动去重。
   */
  function buildApiMessages(): { role: 'user' | 'assistant'; content: string }[] {
    const conv = store.currentConversation
    if (!conv) return []
    // 只取最后一条用户消息（Checkpointer 自动恢复之前的历史）
    const lastUserMsg = [...conv.messages].reverse().find(m => m.role === 'user' && m.content.trim().length > 0)
    if (!lastUserMsg) return []
    return [{ role: 'user' as const, content: lastUserMsg.content }]
  }

  /** 把残留的 running 工具标记为已中断 */
  function _finalizeToolSegments(convId: string, msgId: string, label: string) {
    const msg = store.currentConversation?.messages.find(m => m.id === msgId)
    if (!msg?.segments) return
    const segs = [...msg.segments]
    let changed = false
    for (let i = segs.length - 1; i >= 0; i--) {
      const seg = segs[i]
      if (seg && seg.type === 'tool' && seg.status === 'running') {
        segs[i] = { ...seg, type: 'tool', status: 'done', tool: seg.tool, output: `（${label}）` }
        changed = true
      }
    }
    if (changed) store.updateMessage(convId, msgId, { segments: segs })
  }

  // ==================== 流式期间 debounce 同步 ====================
  // 目的：防止流式中途用户刷新/关闭浏览器导致 assistant 消息内容丢失。
  // 策略：流式回调中调用 _syncStreamedContent，每 2 秒最多同步一次到后端。
  // 同时注册 beforeunload 兜底，页面卸载时用 sendBeacon 发送最后一次状态。

  let _streamSyncTimer: ReturnType<typeof setTimeout> | null = null
  let _streamSyncConvId: string | null = null
  let _streamSyncMsgId: string | null = null
  let _lastSyncedHash = ''

  /** 计算当前 assistant 消息内容的简单 hash，用于判断是否需要同步 */
  function _msgHash(msg: ChatMessage | undefined): string {
    if (!msg) return ''
    return `${msg.content.length}|${msg.reasoning?.length ?? 0}|${msg.segments?.length ?? 0}|${msg.contexts?.length ?? 0}`
  }

  /** 把当前 assistant 消息状态同步到后端（debounce 2 秒） */
  function _syncStreamedContent(convId: string, msgId: string, force = false) {
    _streamSyncConvId = convId
    _streamSyncMsgId = msgId

    if (!force && _streamSyncTimer) return  // 已有定时器在等，不重复设置

    if (_streamSyncTimer) {
      clearTimeout(_streamSyncTimer)
      _streamSyncTimer = null
    }

    if (!force) {
      _streamSyncTimer = setTimeout(() => {
        _streamSyncTimer = null
        _doSyncStreamedContent()
      }, 2000)
    } else {
      _doSyncStreamedContent()
    }
  }

  function _doSyncStreamedContent() {
    const convId = _streamSyncConvId
    const msgId = _streamSyncMsgId
    if (!convId || !msgId) return
    const msg = store.currentConversation?.messages.find(m => m.id === msgId)
    if (!msg) return

    const hash = _msgHash(msg)
    if (hash === _lastSyncedHash) return  // 内容没变化，不同步
    _lastSyncedHash = hash

    import('@/api/conversations').then(mod => {
      callWithRetry(() => mod.updateMessage(convId, msgId, {
        content: msg.content,
        reasoning: msg.reasoning,
        contexts: msg.contexts,
        segments: msg.segments,
        files: msg.files,
      }), true).then(() => store.broadcastChange('updated', convId))
    })
  }

  /** 页面卸载兜底：用 sendBeacon 发送最后一次状态（不保证后端接收，但尽量减少丢失） */
  function _onBeforeUnload() {
    if (_streamSyncConvId && _streamSyncMsgId) {
      const msg = store.currentConversation?.messages.find(m => m.id === _streamSyncMsgId)
      if (msg) {
        const payload = {
          content: msg.content,
          reasoning: msg.reasoning,
          contexts: msg.contexts ?? [],
          segments: msg.segments ?? [],
          files: msg.files ?? [],
        }
        try {
          const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
          navigator.sendBeacon(
            `/api/conversations/${_streamSyncConvId}/messages/${_streamSyncMsgId}`,
            blob,
          )
        } catch {
          // sendBeacon 失败则静默，localStorage 已有最新内容作为兜底
        }
      }
    }
  }

  // 注册 beforeunload（组件挂载期间生效）
  let _unloadRegistered = false
  function _ensureUnloadHook() {
    if (_unloadRegistered) return
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', _onBeforeUnload)
      _unloadRegistered = true
    }
  }

  async function sendMessage(text?: string, uploadedFiles?: { token: string; filename: string; is_image?: boolean }[]) {
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
    store.addMessage(conv.id, { role: 'user', content: q, files: uploadedFiles?.map(f => ({ filename: f.filename, token: f.token, is_image: f.is_image })) })

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

    // 启动流式期间 debounce 同步（防刷新丢数据）
    _ensureUnloadHook()
    _lastSyncedHash = ''

    // 构建请求消息（包含刚添加的用户消息，不含占位的空 assistant）
    const apiMessages = buildApiMessages()

    let abortCalled = false

    abortFn.value = chatStream(
      apiMessages,
      kbStore.currentKbId,
      {
        onContexts: (contexts) => {
          store.updateMessage(conv.id, assistantMsg.id, { contexts })
          _syncStreamedContent(conv.id, assistantMsg.id)
        },
        onReasoning: (token) => {
          const msg = store.currentConversation?.messages.find(m => m.id === assistantMsg.id)
          if (msg) {
            store.updateMessage(conv.id, assistantMsg.id, {
              reasoning: (msg.reasoning ?? '') + token,
            })
            _syncStreamedContent(conv.id, assistantMsg.id)
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
            _syncStreamedContent(conv.id, assistantMsg.id)
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
            _syncStreamedContent(conv.id, assistantMsg.id)
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
            _syncStreamedContent(conv.id, assistantMsg.id)
          }
        },
        onDone: (stats) => {
          loading.value = false
          streaming.value = false
          abortFn.value = null
          if (stats) tokenStats.value = stats
          // 停止流式 debounce 定时器，并立即同步最后一次状态
          if (_streamSyncTimer) {
            clearTimeout(_streamSyncTimer)
            _streamSyncTimer = null
          }
          // 把残留的 running 工具标记为已中断
          _finalizeToolSegments(conv.id, assistantMsg.id, '中断')
          // 流结束后强制同步最后一次到后端（force=true 跳过 debounce）
          _syncStreamedContent(conv.id, assistantMsg.id, true)
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
          // 停止流式 debounce 定时器
          if (_streamSyncTimer) {
            clearTimeout(_streamSyncTimer)
            _streamSyncTimer = null
          }
          // 把残留的 running 工具标记为已中断
          _finalizeToolSegments(conv.id, assistantMsg.id, '中断')
          // 强制同步错误状态到后端
          _syncStreamedContent(conv.id, assistantMsg.id, true)
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
