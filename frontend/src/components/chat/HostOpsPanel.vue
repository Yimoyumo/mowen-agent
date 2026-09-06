<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHostOps, getHostWorkspace, cancelHostOp } from '@/api/hostApi'
import type { HostOpsResult, HostWorkspaceEntry } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  sessionId: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = ref(props.modelValue)
const loading = ref(false)
const ops = ref<HostOpsResult | null>(null)
const workspace = ref<HostWorkspaceEntry[]>([])

const statusLabel: Record<string, string> = {
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  timeout: '超时',
  killed: '已终止',
}

const riskTagType: Record<string, string> = {
  ask: 'warning',
  high: 'danger',
  medium: 'warning',
  low: 'info',
}

let timer: ReturnType<typeof setInterval> | null = null

function startPoll() {
  stopPoll()
  loadAll()
  timer = setInterval(loadAll, 10_000)
}

function stopPoll() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function loadAll() {
  if (!props.sessionId) return
  loading.value = true
  try {
    const [opsRes, wsRes] = await Promise.all([
      getHostOps(props.sessionId, 50),
      getHostWorkspace(props.sessionId, ''),
    ])
    ops.value = opsRes
    workspace.value = wsRes.entries ?? []
  } catch {
    // 后端未就绪 / 无数据，静默
  } finally {
    loading.value = false
  }
}

/** 轮询期间不遮内容：仅首次未拿到数据时显示 loading 遮罩 */
const showMask = computed(() => loading.value && !ops.value)

async function handleCancel(opId: string) {
  try {
    await ElMessageBox.confirm('确定要终止该进程吗？', '终止进程', {
      confirmButtonText: '终止',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await cancelHostOp(opId)
    ElMessage.success('已请求终止')
    await loadAll()
  } catch {
    ElMessage.error('终止失败')
  }
}

function fmtTime(t: number | string | null | undefined): string {
  if (t == null) return '-'
  // 后端时间戳为秒级 epoch；new Date(number) 按毫秒解释，需先换算
  let d: Date
  if (typeof t === 'number') {
    d = new Date(t < 1e12 ? t * 1000 : t)
  } else if (!isNaN(Number(t))) {
    const n = Number(t)
    d = new Date(n < 1e12 ? n * 1000 : n)
  } else {
    d = new Date(t)
  }
  if (Number.isNaN(d.getTime())) return String(t)
  return d.toLocaleString('zh-CN', { hour12: false })
}

watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v) startPoll()
  else stopPoll()
})

function onVisibleChange(v: boolean) {
  emit('update:modelValue', v)
  if (v) startPoll()
  else stopPoll()
}

onMounted(() => {
  if (props.modelValue) startPoll()
})

onBeforeUnmount(stopPoll)
</script>

<template>
  <el-drawer
    :model-value="visible"
    title="宿主执行状态"
    size="460px"
    :destroy-on-close="false"
    @close="() => onVisibleChange(false)"
    @update:model-value="onVisibleChange"
  >
    <div class="host-ops-panel" v-loading="showMask">
      <!-- 运行中进程 -->
      <div class="section">
        <div class="section-title">
          <el-icon><Loading /></el-icon>
          <span>运行中进程</span>
          <span class="section-count" v-if="(ops?.running?.length ?? 0) > 0">{{ ops?.running?.length }}</span>
        </div>
        <div v-if="(ops?.running?.length ?? 0) > 0" class="running-list">
          <div v-for="op in ops.running" :key="op.op_id" class="running-item">
            <div class="running-command">{{ op.command }}</div>
            <div class="running-meta">
              <span>{{ op.session_id }}</span>
              <span>{{ fmtTime(op.started_at) }}</span>
            </div>
            <el-button type="danger" size="small" plain @click="handleCancel(op.op_id)">终止</el-button>
          </div>
        </div>
        <div v-else class="empty-text">暂无运行中进程</div>
      </div>

      <!-- 最近操作审计 -->
      <div class="section">
        <div class="section-title">
          <el-icon><Files /></el-icon>
          <span>最近操作</span>
        </div>
        <el-table :data="ops?.ops ?? []" size="small" class="ops-table" empty-text="暂无操作记录">
          <el-table-column label="时间" width="120">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="工具" width="100">
            <template #default="{ row }">{{ row.tool }}</template>
          </el-table-column>
          <el-table-column label="对象" prop="target" show-overflow-tooltip />
          <el-table-column label="风险" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="(riskTagType[row.risk] as any) || 'info'">{{ row.risk }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'succeeded' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
                {{ statusLabel[row.status] ?? row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 工作区文件树 -->
      <div class="section">
        <div class="section-title">
          <el-icon><FolderOpened /></el-icon>
          <span>工作区文件</span>
        </div>
        <div v-if="workspace.length > 0" class="workspace-list">
          <div v-for="(entry, idx) in workspace" :key="entry.name + idx" class="workspace-item">
            <el-icon>
              <Folder v-if="entry.type === 'dir'" />
              <Document v-else />
            </el-icon>
            <span class="ws-name">{{ entry.name }}</span>
            <span v-if="entry.size != null" class="ws-size">{{ entry.size }} B</span>
          </div>
        </div>
        <div v-else class="empty-text">工作区为空</div>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.host-ops-panel {
  padding-bottom: 24px;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.section-count {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
  background: #f0f0f0;
  border-radius: 999px;
  padding: 0 8px;
}

.empty-text {
  font-size: 12px;
  color: #909399;
  padding: 12px 0;
}

.running-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.running-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fffcf5;
}

.running-command {
  font-size: 13px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  color: #1d1d1d;
  word-break: break-all;
}

.running-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #909399;
}

.running-item .el-button {
  align-self: flex-end;
}

.ops-table {
  width: 100%;
}

.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.workspace-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.workspace-item:hover {
  background: #f5f5f5;
}

.ws-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-size {
  font-size: 11px;
  color: #c0c4cc;
}
</style>
