<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { InteractionRequest, AnswerInteractionPayload } from '@/types/api'

interface Props {
  request?: InteractionRequest | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  answer: [payload: AnswerInteractionPayload]
}>()

const req = computed(() => props.request)

// 倒计时（取请求级 timeout，其次 payload.timeout，最后默认 120s）
const total = computed(() => req.value!.timeout || req.value!.payload.timeout || 120)
const remaining = ref(total.value)
const timedOut = computed(() => remaining.value <= 0)

// 本地已处理态（提交后禁用）
const answered = ref(false)
const submitting = ref(false)

// 审批相关
const approvalScope = ref<'once' | 'session' | 'always'>('once')

// ask_user 相关
const selectedOption = ref('')                 // 单选
const multiOptions = ref<string[]>([])         // 多选
const freeText = ref('')                       // 自由输入

const hasOptions = computed(() =>
  (req.value?.payload.options ?? []).length > 0,
)

let timer: ReturnType<typeof setInterval> | null = null

function startCountdown() {
  stopCountdown()
  remaining.value = total.value
  timer = setInterval(() => {
    remaining.value = Math.max(0, remaining.value - 1)
    if (remaining.value <= 0) stopCountdown()
  }, 1000)
}

function stopCountdown() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => {
  if (req.value) startCountdown()
})
onBeforeUnmount(stopCountdown)

const progressPct = computed(() =>
  Math.max(0, Math.min(100, Math.round((remaining.value / total.value) * 100))),
)

function isAtRisk(now: number) {
  return now <= 10 && now > 0
}

function handleApproval(approved: boolean, scope?: 'once' | 'session' | 'always') {
  if (answered.value || timedOut.value) return
  submitting.value = true
  const payload: AnswerInteractionPayload = approved
    ? { approved: true, scope: scope ?? approvalScope.value }
    : { approved: false }
  emit('answer', payload)
  answered.value = true
  submitting.value = false
}

function handleAskSubmit() {
  if (answered.value || timedOut.value) return
  submitting.value = true

  let answer = freeText.value.trim()
  if (hasOptions.value) {
    if (req.value?.payload.multi_select) {
      answer = multiOptions.value.join(',')
    } else {
      answer = selectedOption.value
    }
  }
  if (!answer) {
    submitting.value = false
    return
  }

  emit('answer', { answer })
  answered.value = true
  submitting.value = false
}
</script>

<template>
  <div v-if="req" class="interaction-card" :class="{ answered, timedOut }">
    <!-- 审批：危险命令确认 -->
    <template v-if="req.kind === 'approval'">
      <el-alert type="warning" :closable="false" show-icon class="interaction-alert">
        <template #title>
          <span class="alert-title">权限审批</span>
        </template>
        <div class="approval-body">
          <div v-if="req.payload.command" class="command-block">
            <span class="detail-label">命令</span>
            <pre class="command-pre">{{ req.payload.command }}</pre>
          </div>
          <div v-if="req.payload.reason" class="reason-row">
            <span class="detail-label">原因</span>
            <span class="reason-text">{{ req.payload.reason }}</span>
          </div>
          <div v-if="req.payload.risk" class="risk-tag">
            风险: {{ req.payload.risk }}
          </div>
        </div>
      </el-alert>

      <div class="action-row">
        <template v-if="!answered && !timedOut">
          <el-button-group>
            <el-button type="success" size="small" :loading="submitting" @click="handleApproval(true, 'once')">允许一次</el-button>
            <el-button type="success" size="small" :loading="submitting" @click="handleApproval(true, 'session')">本会话允许</el-button>
            <el-button type="success" size="small" :loading="submitting" @click="handleApproval(true, 'always')">永久允许</el-button>
          </el-button-group>
          <el-button type="danger" size="small" plain :loading="submitting" @click="handleApproval(false)">拒绝</el-button>
        </template>
        <div v-else-if="timedOut" class="done-hint warn">已超时</div>
        <div v-else class="done-hint">已提交，等待确认…</div>
      </div>
    </template>

    <!-- ask_user：主动提问 -->
    <template v-else>
      <el-alert type="info" :closable="false" show-icon class="interaction-alert">
        <template #title>
          <span class="alert-title">需要您的回答</span>
        </template>
        <div class="ask-body">
          <div class="question-text">{{ req.payload.question }}</div>

          <!-- 预设选项 -->
          <template v-if="hasOptions">
            <el-radio-group v-if="!req.payload.multi_select" v-model="selectedOption" class="option-group">
              <el-radio v-for="opt in req.payload.options ?? []" :key="opt" :value="opt" class="option-item">{{ opt }}</el-radio>
            </el-radio-group>
            <el-checkbox-group v-else v-model="multiOptions" class="option-group">
              <el-checkbox v-for="opt in req.payload.options ?? []" :key="opt" :value="opt" class="option-item">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </template>

          <!-- 自由输入 -->
          <el-input
            v-if="!hasOptions || req.payload.allow_free_text"
            v-model="freeText"
            type="textarea"
            :rows="2"
            :placeholder="hasOptions ? '或自由输入回答' : '请输入您的回答'"
            class="free-text"
          />
        </div>
      </el-alert>

      <div class="action-row">
        <template v-if="!answered && !timedOut">
          <el-button type="primary" size="small" :loading="submitting" @click="handleAskSubmit">
            {{ hasOptions ? '提交选项' : '提交回答' }}
          </el-button>
        </template>
        <div v-else-if="timedOut" class="done-hint warn">已超时</div>
        <div v-else class="done-hint">已提交，等待确认…</div>
      </div>
    </template>

    <!-- 倒计时 -->
    <div class="countdown" v-if="!answered && !timedOut">
      <span class="countdown-text">
        {{ remaining }}s
        <template v-if="isAtRisk(remaining)">（即将超时）</template>
      </span>
      <el-progress
        :percentage="progressPct"
        :stroke-width="4"
        :show-text="false"
        :status="isAtRisk(remaining) ? 'exception' : undefined"
        class="countdown-bar"
      />
    </div>
  </div>
</template>

<style scoped>
.interaction-card {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #f0d8a8;
  border-radius: 8px;
  background: #fffcf5;
}

.interaction-card.answered,
.interaction-card.timedOut {
  border-color: #e4e7ed;
  background: #fafafa;
}

.interaction-alert {
  margin-bottom: 8px;
}

.interaction-alert :deep(.el-alert__title) {
  font-size: 13px;
}

.alert-title {
  font-weight: 600;
}

.approval-body,
.ask-body {
  margin-top: 6px;
}

.detail-label {
  font-size: 12px;
  color: #909399;
  display: block;
  margin-bottom: 4px;
}

.command-block {
  margin-bottom: 8px;
}

.command-pre {
  margin: 0;
  padding: 6px 8px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'SFMono-Regular', Consolas, monospace;
  max-height: 160px;
  overflow-y: auto;
}

.reason-row {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}

.risk-tag {
  display: inline-block;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #fef0f0;
  color: #f56c6c;
}

.question-text {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 10px;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.option-item {
  height: auto;
}

.free-text {
  margin-top: 8px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.done-hint {
  font-size: 12px;
  color: #67c23a;
}

.done-hint.warn {
  color: #e6a23c;
}

.countdown {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.countdown-text {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

.countdown-bar {
  flex: 1;
}
</style>
