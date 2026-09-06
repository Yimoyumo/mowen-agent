<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ExecutorSettingsConfig, ExecutorMode, ApprovalMode } from '@/types/api'

interface Props {
  executor?: ExecutorSettingsConfig
  saving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  save: [config: ExecutorSettingsConfig]
}>()

// 后端未返回时的默认值
const DEFAULT_CONFIG: ExecutorSettingsConfig = {
  mode: 'host',
  approval_mode: 'ask_dangerous',
  approval_timeout: 120,
  ask_timeout: 300,
  command_timeout: 600,
  workspace_retention_days: 7,
}

const mode = ref<ExecutorMode>(props.executor?.mode ?? DEFAULT_CONFIG.mode)
const approvalMode = ref<ApprovalMode>(props.executor?.approval_mode ?? DEFAULT_CONFIG.approval_mode)
const approvalTimeout = ref<number>(props.executor?.approval_timeout ?? DEFAULT_CONFIG.approval_timeout)
const askTimeout = ref<number>(props.executor?.ask_timeout ?? DEFAULT_CONFIG.ask_timeout)
const commandTimeout = ref<number>(props.executor?.command_timeout ?? DEFAULT_CONFIG.command_timeout)
const workspaceRetention = ref<number>(props.executor?.workspace_retention_days ?? DEFAULT_CONFIG.workspace_retention_days)

watch(
  () => props.executor,
  (newVal) => {
    if (!newVal) return
    mode.value = newVal.mode
    approvalMode.value = newVal.approval_mode
    approvalTimeout.value = newVal.approval_timeout
    askTimeout.value = newVal.ask_timeout
    commandTimeout.value = newVal.command_timeout
    workspaceRetention.value = newVal.workspace_retention_days
  },
)

function handleSave() {
  emit('save', {
    mode: mode.value,
    approval_mode: approvalMode.value,
    approval_timeout: approvalTimeout.value,
    ask_timeout: askTimeout.value,
    command_timeout: commandTimeout.value,
    workspace_retention_days: workspaceRetention.value,
  })
}
</script>

<template>
  <div class="executor-settings">
    <h2 class="section-title">执行器</h2>
    <p class="section-desc">
      控制 Agent 工具的执行方式与交互审批策略。宿主机直操模式下，Agent 直接在宿主机执行命令与文件操作。
    </p>

    <el-card shadow="never" class="settings-card">
      <!-- 执行模式 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">执行模式</span>
          <span class="label-desc">工具在何处执行</span>
        </div>
        <div class="setting-control">
          <el-radio-group v-model="mode">
            <el-radio value="host">宿主机直操 (推荐)</el-radio>
            <el-radio value="sandbox">Docker 沙盒</el-radio>
          </el-radio-group>
          <div class="tip">宿主机直操性能更好；沙盒更安全但隔离性更强。</div>
        </div>
      </div>

      <el-divider />

      <!-- 审批模式 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">审批模式</span>
          <span class="label-desc">何时需要用户确认危险命令</span>
        </div>
        <div class="setting-control">
          <el-radio-group v-model="approvalMode">
            <el-radio value="ask_dangerous">危险操作才审批 (推荐)</el-radio>
            <el-radio value="auto">全自动</el-radio>
            <el-radio value="ask_all">全部审批</el-radio>
          </el-radio-group>
          <div class="tip">危险操作才审批可兼顾效率与安全；全自动不打扰但风险更高。</div>
        </div>
      </div>

      <el-divider />

      <!-- 审批超时 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">审批超时(秒)</span>
          <span class="label-desc">审批未响应时的自动超时</span>
        </div>
        <div class="setting-control">
          <el-input-number v-model="approvalTimeout" :min="5" :max="3600" :step="10" />
        </div>
      </div>

      <el-divider />

      <!-- 提问超时 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">提问超时(秒)</span>
          <span class="label-desc">ask_user 提问未响应时的自动超时</span>
        </div>
        <div class="setting-control">
          <el-input-number v-model="askTimeout" :min="5" :max="7200" :step="10" />
        </div>
      </div>

      <el-divider />

      <!-- 命令超时 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">命令超时(秒)</span>
          <span class="label-desc">单条命令执行的最长时长</span>
        </div>
        <div class="setting-control">
          <el-input-number v-model="commandTimeout" :min="5" :max="86400" :step="30" />
        </div>
      </div>

      <el-divider />

      <!-- 工作区保留天数 -->
      <div class="setting-item">
        <div class="setting-label">
          <span class="label-text">工作区保留(天)</span>
          <span class="label-desc">宿主机工作区文件保留天数</span>
        </div>
        <div class="setting-control">
          <el-input-number v-model="workspaceRetention" :min="1" :max="365" />
        </div>
      </div>

      <el-divider />

      <div class="save-area">
        <el-button type="primary" :loading="saving" @click="handleSave">
          保存
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
}

.settings-card {
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.setting-item {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.setting-label {
  min-width: 180px;
  flex-shrink: 0;
}

.label-text {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.label-desc {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.setting-control {
  flex: 1;
  min-width: 0;
}

.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.save-area {
  display: flex;
  justify-content: flex-end;
}
</style>
