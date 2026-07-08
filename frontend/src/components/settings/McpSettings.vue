<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getExtensions,
  addMcpServer,
  updateMcpServer,
  deleteMcpServer,
  getSettings,
  updateSettings,
  type McpServerInfo,
} from '@/api/settingsApi'

interface McpServer extends McpServerInfo {
  editing?: boolean
}

const servers = ref<McpServer[]>([])
const loading = ref(false)

// JSON 编辑器
const jsonText = ref('')
const jsonEditing = ref(false)
const jsonError = ref('')

// 从 settings 生成 JSON 文本
function buildJson() {
  const obj: Record<string, any> = {}
  for (const s of servers.value) {
    const entry: any = { transport: s.transport }
    if (s.transport === 'stdio') {
      entry.command = s.command
      entry.args = s.args
    } else {
      entry.url = s.url
    }
    obj[s.name] = entry
  }
  jsonText.value = JSON.stringify(obj, null, 2)
}

async function saveJson() {
  // 验证 JSON
  let parsed: any
  try {
    parsed = JSON.parse(jsonText.value)
  } catch (e: any) {
    jsonError.value = `JSON 格式错误: ${e.message}`
    return
  }

  if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
    jsonError.value = '必须是 JSON 对象，如 {"server_name": {...}}'
    return
  }

  // 校验每个条目
  for (const [name, cfg] of Object.entries(parsed)) {
    const c = cfg as any
    if (!c.transport || !['stdio', 'sse'].includes(c.transport)) {
      jsonError.value = `「${name}」的 transport 必须是 stdio 或 sse`
      return
    }
    if (c.transport === 'stdio' && !c.command) {
      jsonError.value = `「${name}」是 stdio 模式，需要 command 字段`
      return
    }
    if (c.transport === 'sse' && !c.url) {
      jsonError.value = `「${name}」是 sse 模式，需要 url 字段`
      return
    }
  }

  jsonError.value = ''
  try {
    // 直接整体更新 mcp_servers
    const settings = await getSettings()
    settings.mcp_servers = parsed
    await updateSettings({ mcp_servers: parsed })
    ElMessage.success('JSON 配置已保存')
    jsonEditing.value = false
    await load()
  } catch (e: any) {
    jsonError.value = e?.response?.data?.message || '保存失败'
  }
}

function startJsonEdit() {
  buildJson()
  jsonEditing.value = true
  jsonError.value = ''
}

function cancelJsonEdit() {
  jsonEditing.value = false
  jsonError.value = ''
}

// 新增表单
const showAddDialog = ref(false)
const addForm = ref({
  name: '',
  transport: 'stdio' as 'stdio' | 'sse',
  command: '',
  args: '',
  url: '',
})

async function load() {
  loading.value = true
  try {
    const data = await getExtensions()
    servers.value = data.mcp_servers.map(s => ({ ...s, editing: false }))
    buildJson()
  } catch {
    ElMessage.error('加载 MCP 配置失败')
  } finally {
    loading.value = false
  }
}

async function handleAdd() {
  if (!addForm.value.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (addForm.value.transport === 'stdio' && !addForm.value.command.trim()) {
    ElMessage.warning('stdio 模式需要填写 command')
    return
  }
  if (addForm.value.transport === 'sse' && !addForm.value.url.trim()) {
    ElMessage.warning('SSE 模式需要填写 URL')
    return
  }

  try {
    await addMcpServer({
      name: addForm.value.name.trim(),
      transport: addForm.value.transport,
      command: addForm.value.command,
      args: addForm.value.args.split(/\s+/).filter(Boolean),
      url: addForm.value.url,
    })
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addForm.value = { name: '', transport: 'stdio', command: '', args: '', url: '' }
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '添加失败')
  }
}

async function handleDelete(name: string) {
  try {
    await ElMessageBox.confirm(`确认删除 MCP 服务器「${name}」？`, '删除确认', { type: 'warning' })
    await deleteMcpServer(name)
    ElMessage.success('已删除')
    await load()
  } catch {
    // 取消
  }
}

// 编辑
const editForm = ref<{ command: string; args: string; url: string }>({ command: '', args: '', url: '' })

function startEdit(s: McpServer) {
  s.editing = true
  editForm.value = {
    command: s.command,
    args: s.args.join(' '),
    url: s.url,
  }
}

async function saveEdit(s: McpServer) {
  try {
    await updateMcpServer(s.name, {
      command: editForm.value.command,
      args: editForm.value.args.split(/\s+/).filter(Boolean),
      url: editForm.value.url,
    })
    ElMessage.success('已保存')
    s.editing = false
    await load()
  } catch {
    ElMessage.error('保存失败')
  }
}

function cancelEdit(s: McpServer) {
  s.editing = false
}

onMounted(load)
</script>

<template>
  <div class="mcp-settings" v-loading="loading">
    <div class="section-header">
      <div class="section-title">
        <el-icon><Connection /></el-icon>
        <h3>MCP 服务器</h3>
      </div>
      <el-button type="primary" size="small" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>
        添加
      </el-button>
    </div>

    <el-alert type="info" :closable="false" class="hint">
      MCP（Model Context Protocol）服务器为 Agent 提供额外的工具能力。stdio 模式通过命令启动，SSE 模式连接远程服务。
    </el-alert>

    <!-- 服务器列表 -->
    <div v-if="servers.length === 0" class="empty">
      暂未配置 MCP 服务器，点击「添加」开始配置
    </div>

    <div v-for="s in servers" :key="s.name" class="server-card">
      <div class="card-header">
        <div class="card-title">
          <span class="server-name">{{ s.name }}</span>
          <el-tag size="small" :type="s.transport === 'stdio' ? 'info' : 'success'">{{ s.transport }}</el-tag>
        </div>
        <div class="card-actions">
          <el-button v-if="!s.editing" link size="small" @click="startEdit(s)">编辑</el-button>
          <el-button v-if="!s.editing" link type="danger" size="small" @click="handleDelete(s.name)">删除</el-button>
          <el-button v-if="s.editing" link type="success" size="small" @click="saveEdit(s)">保存</el-button>
          <el-button v-if="s.editing" link size="small" @click="cancelEdit(s)">取消</el-button>
        </div>
      </div>

      <!-- 查看模式 -->
      <div v-if="!s.editing" class="card-body">
        <div v-if="s.transport === 'stdio'" class="field">
          <span class="field-label">命令</span>
          <code class="field-value">{{ s.command }} {{ s.args.join(' ') }}</code>
        </div>
        <div v-else class="field">
          <span class="field-label">URL</span>
          <code class="field-value">{{ s.url }}</code>
        </div>
      </div>

      <!-- 编辑模式 -->
      <div v-else class="card-body">
        <div v-if="s.transport === 'stdio'" class="edit-fields">
          <el-input v-model="editForm.command" placeholder="命令，如 npx" size="small" />
          <el-input v-model="editForm.args" placeholder="参数，空格分隔，如 -y @modelcontextprotocol/server-filesystem /tmp" size="small" />
        </div>
        <div v-else>
          <el-input v-model="editForm.url" placeholder="SSE 服务 URL" size="small" />
        </div>
      </div>
    </div>

    <!-- JSON 编辑器 -->
    <el-divider content-position="left">高级：直接编辑 JSON</el-divider>
    <div v-if="!jsonEditing" class="json-preview">
      <pre>{{ jsonText }}</pre>
      <el-button size="small" @click="startJsonEdit">编辑 JSON</el-button>
    </div>
    <div v-else class="json-editor-wrap">
      <el-input
        v-model="jsonText"
        type="textarea"
        :rows="12"
        placeholder='{\n  "filesystem": {\n    "command": "npx",\n    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],\n    "transport": "stdio"\n  }\n}'
        class="json-textarea"
        style="font-family: monospace; font-size: 12px"
      />
      <div v-if="jsonError" class="json-error">{{ jsonError }}</div>
      <div class="json-actions">
        <el-button size="small" @click="cancelJsonEdit">取消</el-button>
        <el-button size="small" type="primary" @click="saveJson">保存</el-button>
      </div>
    </div>

    <!-- 添加对话框 -->
    <el-dialog v-model="showAddDialog" title="添加 MCP 服务器" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="addForm.name" placeholder="如 filesystem、github" />
        </el-form-item>
        <el-form-item label="传输方式">
          <el-radio-group v-model="addForm.transport">
            <el-radio value="stdio">stdio（本地命令）</el-radio>
            <el-radio value="sse">SSE（远程服务）</el-radio>
            <el-radio value="http">HTTP（Streamable HTTP）</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="addForm.transport === 'stdio'">
          <el-form-item label="命令">
            <el-input v-model="addForm.command" placeholder="如 npx" />
          </el-form-item>
          <el-form-item label="参数">
            <el-input v-model="addForm.args" placeholder="空格分隔，如 -y @modelcontextprotocol/server-filesystem /tmp" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="URL">
            <el-input v-model="addForm.url" placeholder="如 https://mcp.grep.app" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mcp-settings {
  max-width: 700px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title h3 {
  margin: 0;
  font-size: 16px;
}

.hint {
  margin-bottom: 16px;
}

.empty {
  color: #909399;
  text-align: center;
  padding: 40px 0;
}

.server-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fff;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.server-name {
  font-weight: 600;
  font-size: 14px;
}

.card-actions {
  display: flex;
  gap: 4px;
}

.card-body {
  font-size: 13px;
}

.field {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.field-label {
  color: #909399;
  flex-shrink: 0;
  width: 40px;
}

.field-value {
  font-family: monospace;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}

.edit-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.json-preview {
  position: relative;
}

.json-preview pre {
  background: #1d1d1d;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 12px;
  font-family: monospace;
  overflow-x: auto;
  margin: 0 0 8px 0;
  max-height: 300px;
  overflow-y: auto;
}

.json-preview .el-button {
  margin-top: 4px;
}

.json-editor-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.json-textarea :deep(.el-textarea__inner) {
  font-family: monospace !important;
  font-size: 12px !important;
  line-height: 1.6 !important;
}

.json-error {
  color: #f56c6c;
  font-size: 12px;
  padding: 4px 0;
}

.json-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
