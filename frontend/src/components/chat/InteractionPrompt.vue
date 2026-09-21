<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import type { AnswerInteractionPayload, InteractionRequest } from '@/types/api'

/**
 * 停靠在输入框上方的 HITL 提示条（审批 / ask_user）。
 *
 * 之所以放在输入框而不是消息流里：工具卡默认折叠，审批请求容易被埋在
 * 长回复中间而错过；停靠后与用户当前操作焦点同屏，始终可见。
 */

const store = useChatStore()

/** 当前会话的待处理交互：审批优先，其余按到达顺序排队 */
const queue = computed<InteractionRequest[]>(() => {
  const cid = store.currentId
  return store.pendingInteractions
    .filter(r => !r._convId || r._convId === cid)
    .slice()
    .sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'approval' ? -1 : 1
      return (a.created_at ?? 0) - (b.created_at ?? 0)
    })
})

const req = computed<InteractionRequest | null>(() => queue.value[0] ?? null)
const queuedCount = computed(() => Math.max(0, queue.value.length - 1))

const isApproval = computed(() => req.value?.kind === 'approval')
const hasOptions = computed(() => (req.value?.payload.options ?? []).length > 0)

// ==================== 倒计时 ====================

const total = computed(() => req.value?.timeout || req.value?.payload.timeout || 120)
const remaining = ref(total.value)
const timedOut = computed(() => req.value !== null && remaining.value <= 0)
const atRisk = computed(() => remaining.value <= 10 && remaining.value > 0)
const progressPct = computed(() =>
  Math.max(0, Math.min(100, Math.round((remaining.value / total.value) * 100))),
)

let timer: ReturnType<typeof setInterval> | null = null

function stopCountdown() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function startCountdown() {
  stopCountdown()
  remaining.value = total.value
  if (!req.value) return
  timer = setInterval(() => {
    remaining.value = Math.max(0, remaining.value - 1)
    if (remaining.value <= 0) stopCountdown()
  }, 1000)
}

onBeforeUnmount(stopCountdown)

// ==================== 本地应答状态 ====================

const submitting = ref(false)
const approvalScope = ref<'once' | 'session' | 'always'>('once')
const selectedOption = ref('')
const multiOptions = ref<string[]>([])
const freeText = ref('')

/** 请求切换（上一条已处理 / 队列前移）时重置本地输入并重启倒计时 */
watch(() => req.value?.request_id, () => {
  stopCountdown()
  submitting.value = false
  approvalScope.value = 'once'
  selectedOption.value = ''
  multiOptions.value = []
  freeText.value = ''
  startCountdown()
}, { immediate: true })

async function submit(payload: AnswerInteractionPayload) {
  const id = req.value?.request_id
  if (!id || submitting.value || timedOut.value) return
  submitting.value = true
  const ok = await store.answerInteraction(id, payload)
  submitting.value = false
  // 成功时该请求已从 pending 中移除，队列自动前移；失败则保留卡片让用户重试
  if (!ok) ElMessage.error('提交失败，请重试')
}

function handleApproval(approved: boolean, scope?: 'once' | 'session' | 'always') {
  submit(approved ? { approved: true, scope: scope ?? approvalScope.value } : { approved: false })
}

function handleAskSubmit() {
  const answer = hasOptions.value
    ? (req.value?.payload.multi_select ? multiOptions.value.join(',') : selectedOption.value)
    : freeText.value.trim()
  if (!answer) {
    ElMessage.warning('请先选择或输入回答')
    return
  }
  submit({ answer })
}
</script>

<template>
  <div class="interaction-dock">
    <Transition name="prompt-slide">
      <div
        v-if="req"
        class="interaction-prompt"
        :class="[req.kind, { timeout: timedOut }]"
      >
        <!-- 头部：类型 / 关联工具 / 排队数 / 倒计时 -->
        <div class="prompt-head">
          <span class="prompt-badge">
            <el-icon><Warning v-if="isApproval" /><ChatDotRound v-else /></el-icon>
          </span>
          <span class="prompt-title">{{ isApproval ? '权限审批' : '需要您的回答' }}</span>
          <span v-if="isApproval && req.payload.tool" class="prompt-tool">{{ req.payload.tool }}</span>
          <span v-if="queuedCount > 0" class="prompt-queue">还有 {{ queuedCount }} 个待处理</span>
          <span class="prompt-timer" :class="{ risk: atRisk }">
            <el-icon><Timer /></el-icon>{{ remaining }}s
          </span>
        </div>

        <el-progress
          :percentage="progressPct"
          :stroke-width="3"
          :show-text="false"
          :status="atRisk ? 'exception' : undefined"
          class="prompt-progress"
        />

        <!-- 审批：命令详情 -->
        <div v-if="isApproval" class="prompt-body">
          <div v-if="req.payload.command" class="command-block">
            <span class="detail-label">命令</span>
            <pre class="command-pre">{{ req.payload.command }}</pre>
          </div>
          <div class="meta-row">
            <span v-if="req.payload.reason" class="meta-item">
              <span class="detail-label inline">原因</span>{{ req.payload.reason }}
            </span>
            <span v-if="req.payload.risk" class="risk-tag">风险 {{ req.payload.risk }}</span>
          </div>
        </div>

        <!-- ask_user：问题与选项 -->
        <div v-else class="prompt-body">
          <div class="question-text">{{ req.payload.question }}</div>

          <template v-if="hasOptions">
            <el-radio-group v-if="!req.payload.multi_select" v-model="selectedOption" class="option-group">
              <el-radio v-for="opt in req.payload.options ?? []" :key="opt" :value="opt" class="option-item">{{ opt }}</el-radio>
            </el-radio-group>
            <el-checkbox-group v-else v-model="multiOptions" class="option-group">
              <el-checkbox v-for="opt in req.payload.options ?? []" :key="opt" :value="opt" class="option-item">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </template>

          <el-input
            v-if="!hasOptions || req.payload.allow_free_text"
            v-model="freeText"
            type="textarea"
            :rows="2"
            :placeholder="hasOptions ? '或自由输入回答' : '请输入您的回答'"
            class="free-text"
          />
        </div>

        <!-- 操作区 -->
        <div class="prompt-actions">
          <template v-if="!timedOut">
            <template v-if="isApproval">
              <el-button type="success" size="small" :loading="submitting" @click="handleApproval(true, 'once')">允许一次</el-button>
              <el-button type="success" size="small" plain :loading="submitting" @click="handleApproval(true, 'session')">本会话允许</el-button>
              <el-button type="success" size="small" plain :loading="submitting" @click="handleApproval(true, 'always')">永久允许</el-button>
              <span class="actions-spacer" />
              <el-button type="danger" size="small" plain :loading="submitting" @click="handleApproval(false)">拒绝</el-button>
            </template>
            <template v-else>
              <el-button type="primary" size="small" :loading="submitting" @click="handleAskSubmit">
                {{ hasOptions ? '提交选项' : '提交回答' }}
              </el-button>
            </template>
          </template>
          <div v-else class="timeout-hint">
            <el-icon><WarningFilled /></el-icon>
            <span>已超时，等待后端回收该请求…</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.interaction-dock {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 0 24px;
  flex-shrink: 0;
}

.interaction-prompt {
  border: 1px solid #f0d8a8;
  border-left: 3px solid #e6a23c;
  border-radius: 14px;
  background: #fffcf5;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  padding: 10px 14px 12px;
}

.interaction-prompt.ask_user {
  border-color: #b8d8f8;
  border-left-color: #409eff;
  background: #f7fbff;
}

.interaction-prompt.timeout {
  border-color: #e4e7ed;
  border-left-color: #c0c4cc;
  background: #fafafa;
}

/* 头部 */
.prompt-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.prompt-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: #fdf0d5;
  color: #e6a23c;
  font-size: 13px;
  flex-shrink: 0;
}

.interaction-prompt.ask_user .prompt-badge {
  background: #e8f2ff;
  color: #409eff;
}

.prompt-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  flex-shrink: 0;
}

.prompt-tool {
  font-size: 11px;
  color: #606266;
  background: #f0f2f5;
  border-radius: 999px;
  padding: 1px 8px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prompt-queue {
  font-size: 11px;
  color: #909399;
}

.prompt-timer {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  font-size: 11px;
  color: #909399;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.prompt-timer.risk {
  color: #f56c6c;
  font-weight: 600;
}

.prompt-progress {
  margin-bottom: 8px;
}

/* 主体 */
.prompt-body {
  max-height: 200px;
  overflow-y: auto;
}

.detail-label {
  font-size: 11px;
  color: #909399;
}

.detail-label.inline {
  margin-right: 4px;
}

.command-block {
  margin-bottom: 6px;
}

.command-pre {
  margin: 4px 0 0;
  padding: 6px 10px;
  background: #fff;
  border: 1px solid #f0e0c0;
  border-radius: 6px;
  font-size: 12px;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'SFMono-Regular', Consolas, monospace;
  max-height: 120px;
  overflow-y: auto;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
}

.risk-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: #fef0f0;
  color: #f56c6c;
}

.question-text {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 8px;
}

.option-group {
  display: flex;
  flex-direction: column;
  /* 覆盖 el-radio-group / el-checkbox-group 自带的 align-items: center，
     否则纵向排列后选项会被横向居中，与上方问题文字错位 */
  align-items: stretch;
  gap: 2px;
}

.option-item {
  height: auto;
  margin-right: 0;
}

.free-text {
  margin-top: 8px;
}

/* 操作区 */
.prompt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.actions-spacer {
  flex: 1;
}

.timeout-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #e6a23c;
}

/* 出现 / 消失动画 */
.prompt-slide-enter-active,
.prompt-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.prompt-slide-enter-from,
.prompt-slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
