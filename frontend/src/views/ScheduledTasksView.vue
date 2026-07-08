<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listScheduledTasks,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  pauseScheduledTask,
  resumeScheduledTask,
  runScheduledTaskNow,
  getScheduledTaskConversation,
} from '@/api/scheduledTaskApi'
import { getKnowledgeBases } from '@/api/knowledgeBaseApi'
import type { ScheduledTask, ScheduleType, TaskStatus } from '@/types/api'
import type { KnowledgeBase } from '@/types/api'

const router = useRouter()
const tasks = ref<ScheduledTask[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingTask = ref<ScheduledTask | null>(null)
const saving = ref(false)
const knowledgeBases = ref<KnowledgeBase[]>([])

// 表单数据
const formData = ref({
  name: '',
  prompt: '',
  schedule_type: 'cron' as ScheduleType,
  schedule_config: {
    expression: '',
    seconds: 3600,
    datetime: '',
  },
  kb_id: '' as string,
})

// cron 预设
const cronPresets = [
  { label: '每天 9:00', value: '0 9 * * *' },
  { label: '每天 18:00', value: '0 18 * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '每 30 分钟', value: '*/30 * * * *' },
  { label: '每周一 9:00', value: '0 9 * * 1' },
  { label: '每月 1 号 9:00', value: '0 9 1 * *' },
]

// interval 预设
const intervalPresets = [
  { label: '5 分钟', value: 300 },
  { label: '30 分钟', value: 1800 },
  { label: '1 小时', value: 3600 },
  { label: '6 小时', value: 21600 },
  { label: '12 小时', value: 43200 },
  { label: '1 天', value: 86400 },
]

const dialogTitle = computed(() => editingTask.value ? '编辑定时任务' : '创建定时任务')

const scheduleConfigForSubmit = computed(() => {
  const sc = formData.value.schedule_config
  if (formData.value.schedule_type === 'cron') {
    return { expression: sc.expression }
  } else if (formData.value.schedule_type === 'interval') {
    return { seconds: sc.seconds }
  } else {
    return { datetime: sc.datetime }
  }
})

// 对话历史查看
const historyDialogVisible = ref(false)
const historyTask = ref<ScheduledTask | null>(null)
const historyMessages = ref<any[]>([])
const historyLoading = ref(false)

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = await listScheduledTasks()
  } catch {
    ElMessage.error('加载定时任务失败')
  } finally {
    loading.value = false
  }
}

async function loadKnowledgeBases() {
  try {
    const res = await getKnowledgeBases()
    knowledgeBases.value = res
  } catch {
    // 静默
  }
}

function openCreateDialog() {
  editingTask.value = null
  formData.value = {
    name: '',
    prompt: '',
    schedule_type: 'cron',
    schedule_config: {
      expression: '0 9 * * *',
      seconds: 3600,
      datetime: '',
    },
    kb_id: '',
  }
  dialogVisible.value = true
}

function openEditDialog(task: ScheduledTask) {
  editingTask.value = task
  formData.value = {
    name: task.name,
    prompt: task.prompt,
    schedule_type: task.schedule_type,
    schedule_config: {
      expression: task.schedule_config.expression || '0 9 * * *',
      seconds: task.schedule_config.seconds || 3600,
      datetime: task.schedule_config.datetime || '',
    },
    kb_id: task.kb_id || '',
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!formData.value.name.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  if (!formData.value.prompt.trim()) {
    ElMessage.warning('请输入提示词')
    return
  }

  saving.value = true
  const payload = {
    name: formData.value.name.trim(),
    prompt: formData.value.prompt.trim(),
    schedule_type: formData.value.schedule_type,
    schedule_config: scheduleConfigForSubmit.value,
    kb_id: formData.value.kb_id || null,
  }

  try {
    if (editingTask.value) {
      await updateScheduledTask(editingTask.value.id, payload)
      ElMessage.success('任务已更新')
    } else {
      await createScheduledTask(payload as any)
      ElMessage.success('任务已创建')
    }
    dialogVisible.value = false
    await loadTasks()
  } catch (err: any) {
    const msg = err?.response?.data?.message || '操作失败'
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

async function handleDelete(task: ScheduledTask) {
  try {
    await ElMessageBox.confirm(
      `确定要删除定时任务"${task.name}"吗？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteScheduledTask(task.id)
    ElMessage.success('任务已删除')
    await loadTasks()
  } catch {
    // 用户取消
  }
}

async function handlePause(task: ScheduledTask) {
  try {
    await pauseScheduledTask(task.id)
    ElMessage.success('任务已暂停')
    await loadTasks()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleResume(task: ScheduledTask) {
  try {
    await resumeScheduledTask(task.id)
    ElMessage.success('任务已恢复')
    await loadTasks()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleRunNow(task: ScheduledTask) {
  try {
    await runScheduledTaskNow(task.id)
    ElMessage.success('任务已触发')
    // 3 秒后刷新状态
    setTimeout(() => loadTasks(), 3000)
  } catch {
    ElMessage.error('触发失败')
  }
}

async function handleViewHistory(task: ScheduledTask) {
  historyTask.value = task
  historyDialogVisible.value = true
  historyLoading.value = true
  historyMessages.value = []
  try {
    const res = await getScheduledTaskConversation(task.id)
    historyMessages.value = (res as any).messages || []
  } catch {
    ElMessage.error('加载历史失败')
  } finally {
    historyLoading.value = false
  }
}

function goBack() {
  router.push('/')
}

// 工具函数
function statusTag(status: TaskStatus): { type: string; text: string } {
  switch (status) {
    case 'active': return { type: 'success', text: '运行中' }
    case 'paused': return { type: 'info', text: '已暂停' }
    case 'completed': return { type: '', text: '已完成' }
    case 'error': return { type: 'danger', text: '出错' }
    default: return { type: '', text: status }
  }
}

function formatSchedule(task: ScheduledTask): string {
  const cfg = task.schedule_config
  if (task.schedule_type === 'cron') {
    return `Cron: ${cfg.expression || '?'}`
  } else if (task.schedule_type === 'interval') {
    const s = cfg.seconds || 0
    if (s >= 86400) return `每 ${Math.floor(s / 86400)} 天`
    if (s >= 3600) return `每 ${Math.floor(s / 3600)} 小时`
    if (s >= 60) return `每 ${Math.floor(s / 60)} 分钟`
    return `每 ${s} 秒`
  } else {
    return `单次: ${cfg.datetime || '?'}`
  }
}

function formatTime(ts: number | null): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  loadTasks()
  loadKnowledgeBases()
})
</script>

<template>
  <div class="scheduled-tasks-page">
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>返回</span>
        </button>
        <h1 class="page-title">定时任务</h1>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>
        <span>创建任务</span>
      </el-button>
    </header>

    <div v-loading="loading" class="page-body">
      <el-empty v-if="tasks.length === 0 && !loading" description="还没有定时任务">
        <el-button type="primary" @click="openCreateDialog">创建第一个任务</el-button>
      </el-empty>

      <div v-else class="task-list">
        <el-card v-for="task in tasks" :key="task.id" class="task-card" shadow="hover">
          <div class="task-header">
            <div class="task-title-row">
              <span class="task-name">{{ task.name }}</span>
              <el-tag :type="statusTag(task.status).type as any" size="small" effect="light">
                {{ statusTag(task.status).text }}
              </el-tag>
              <span class="task-schedule-tag">{{ formatSchedule(task) }}</span>
            </div>
            <div class="task-actions">
              <el-button text size="small" @click="handleRunNow(task)" title="立即执行">
                <el-icon><VideoPlay /></el-icon>
              </el-button>
              <el-button text size="small" @click="openEditDialog(task)" title="编辑">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text size="small" @click="handleViewHistory(task)" title="执行历史">
                <el-icon><Clock /></el-icon>
              </el-button>
              <el-button v-if="task.status === 'active'" text size="small" type="warning" @click="handlePause(task)" title="暂停">
                <el-icon><VideoPause /></el-icon>
              </el-button>
              <el-button v-if="task.status === 'paused'" text size="small" type="success" @click="handleResume(task)" title="恢复">
                <el-icon><RefreshRight /></el-icon>
              </el-button>
              <el-button text size="small" type="danger" @click="handleDelete(task)" title="删除">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>

          <div class="task-prompt">
            <el-icon class="prompt-icon"><ChatLineSquare /></el-icon>
            <span>{{ task.prompt }}</span>
          </div>

          <div class="task-meta">
            <span class="meta-item" v-if="task.next_run_at">
              <el-icon><Timer /></el-icon>
              下次: {{ formatTime(task.next_run_at) }}
            </span>
            <span class="meta-item" v-if="task.last_run_at">
              <el-icon><CircleCheck /></el-icon>
              上次: {{ formatTime(task.last_run_at) }}
            </span>
            <span class="meta-item">
              <el-icon><DataLine /></el-icon>
              执行 {{ task.run_count }} 次
            </span>
            <span class="meta-item" v-if="task.kb_id">
              <el-icon><FolderOpened /></el-icon>
              知识库
            </span>
          </div>

          <div v-if="task.last_result" class="task-result" :class="{ error: task.status === 'error' }">
            {{ task.last_result }}
          </div>
        </el-card>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px" :close-on-click-modal="false">
      <el-form :model="formData" label-width="100px" label-position="top">
        <el-form-item label="任务名称">
          <el-input v-model="formData.name" placeholder="如：每日新闻摘要" />
        </el-form-item>

        <el-form-item label="提示词">
          <el-input
            v-model="formData.prompt"
            type="textarea"
            :rows="4"
            placeholder="输入希望 AI 定时执行的任务提示词，如：请帮我搜索今天的科技新闻并总结要点"
          />
        </el-form-item>

        <el-form-item label="调度类型">
          <el-radio-group v-model="formData.schedule_type">
            <el-radio-button value="cron">Cron 表达式</el-radio-button>
            <el-radio-button value="interval">固定间隔</el-radio-button>
            <el-radio-button value="once">定时一次</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- Cron 配置 -->
        <el-form-item v-if="formData.schedule_type === 'cron'" label="Cron 表达式">
          <el-input v-model="formData.schedule_config.expression" placeholder="分 时 日 月 周 (如 0 9 * * *)" />
          <div class="preset-tags">
            <el-tag
              v-for="preset in cronPresets"
              :key="preset.value"
              class="preset-tag"
              effect="plain"
              @click="formData.schedule_config.expression = preset.value"
            >
              {{ preset.label }}
            </el-tag>
          </div>
          <div class="cron-hint">
            格式: 分(0-59) 时(0-23) 日(1-31) 月(1-12) 周(0-6, 0=周日)<br>
            示例: <code>0 9 * * *</code> = 每天 9:00, <code>*/30 * * * *</code> = 每 30 分钟
          </div>
        </el-form-item>

        <!-- Interval 配置 -->
        <el-form-item v-if="formData.schedule_type === 'interval'" label="执行间隔">
          <el-input-number v-model="formData.schedule_config.seconds" :min="60" :step="60" />
          <span class="interval-unit">秒</span>
          <div class="preset-tags">
            <el-tag
              v-for="preset in intervalPresets"
              :key="preset.value"
              class="preset-tag"
              effect="plain"
              @click="formData.schedule_config.seconds = preset.value"
            >
              {{ preset.label }}
            </el-tag>
          </div>
        </el-form-item>

        <!-- Once 配置 -->
        <el-form-item v-if="formData.schedule_type === 'once'" label="执行时间">
          <el-input v-model="formData.schedule_config.datetime" placeholder="2024-12-25T09:00:00" />
          <div class="cron-hint">
            ISO 8601 格式: YYYY-MM-DDTHH:MM:SS
          </div>
        </el-form-item>

        <!-- 知识库关联 -->
        <el-form-item label="关联知识库 (可选)">
          <el-select v-model="formData.kb_id" placeholder="不关联" clearable style="width: 100%">
            <el-option
              v-for="kb in knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">确定</el-button>
      </template>
    </el-dialog>

    <!-- 执行历史对话框 -->
    <el-dialog v-model="historyDialogVisible" :title="`执行历史 - ${historyTask?.name || ''}`" width="700px">
      <div v-loading="historyLoading">
        <el-empty v-if="historyMessages.length === 0 && !historyLoading" description="还没有执行记录" />
        <div v-else class="history-list">
          <div v-for="(msg, idx) in historyMessages" :key="idx" class="history-msg" :class="msg.role">
            <div class="history-msg-role">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else><ChatDotSquare /></el-icon>
              {{ msg.role === 'user' ? '提示词' : 'AI 回复' }}
              <span class="history-msg-time">{{ formatTime(msg.createdAt) }}</span>
            </div>
            <div class="history-msg-content">{{ msg.content }}</div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.scheduled-tasks-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  border-color: #1d1d1d;
  color: #1d1d1d;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.page-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 900px;
  margin: 0 auto;
}

.task-card {
  border-radius: 12px;
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.task-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.task-schedule-tag {
  font-size: 12px;
  color: #909399;
  background: #f4f4f5;
  padding: 2px 8px;
  border-radius: 4px;
}

.task-actions {
  display: flex;
  gap: 2px;
}

.task-prompt {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 8px;
}

.prompt-icon {
  margin-top: 2px;
  flex-shrink: 0;
  color: #c0c4cc;
}

.task-prompt span {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #909399;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-result {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
  border-left: 3px solid #409eff;
  word-break: break-all;
}

.task-result.error {
  background: #fef0f0;
  border-left-color: #f56c6c;
  color: #f56c6c;
}

/* 对话框内样式 */
.preset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.preset-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.preset-tag:hover {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}

.cron-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

.cron-hint code {
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
}

.interval-unit {
  margin-left: 8px;
  color: #909399;
}

/* 历史对话框 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-msg {
  border-radius: 8px;
  padding: 12px;
}

.history-msg.user {
  background: #ecf5ff;
}

.history-msg.assistant {
  background: #f4f4f5;
}

.history-msg-role {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 6px;
}

.history-msg-time {
  font-weight: 400;
  font-size: 12px;
  color: #c0c4cc;
  margin-left: 8px;
}

.history-msg-content {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
