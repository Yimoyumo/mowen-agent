import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AxiosError } from 'axios'
import {
  getKnowledgeBases,
  getKnowledgeBaseTypes,
  createKnowledgeBase,
  deleteKnowledgeBase,
  buildKnowledgeBase,
  uploadDocumentToKnowledgeBase,
} from '@/api/knowledgeBaseApi'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import type { CreateKnowledgeBaseRequest, KnowledgeBaseType } from '@/types/api'

export function useKnowledgeBaseManager() {
  const store = useKnowledgeBaseStore()
  const creating = ref(false)
  const building = ref(false)
  const uploading = ref(false)
  const kbTypes = ref<KnowledgeBaseType[]>([
    { value: 'novel', label: '小说' },
    { value: 'tech', label: '技术文档' },
    { value: 'project', label: '项目文档' },
    { value: 'book', label: '专业书籍' },
    { value: 'general', label: '通用文档' },
  ])

  async function loadKbTypes() {
    try {
      const types = await getKnowledgeBaseTypes()
      kbTypes.value = types
    } catch {
      // 使用默认类型
    }
  }

  async function loadList() {
    store.setLoading(true)
    try {
      const list = await getKnowledgeBases()
      store.setKnowledgeBases(list)
      // 不自动选择知识库，由用户主动选择是否启用 RAG
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      ElMessage.error(axiosErr.response?.data?.detail || '加载知识库失败')
    } finally {
      store.setLoading(false)
    }
  }

  async function handleCreate(payload: CreateKnowledgeBaseRequest) {
    if (!payload.name.trim()) {
      ElMessage.warning('请输入知识库名称')
      return
    }

    creating.value = true
    try {
      const kb = await createKnowledgeBase({
        name: payload.name.trim(),
        description: payload.description?.trim() ?? '',
        kb_type: payload.kb_type || 'general',
      })
      store.addKnowledgeBase(kb)
      store.setCurrentKbId(kb.id)
      ElMessage.success(`知识库 ${kb.name} 创建成功`)
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      ElMessage.error(axiosErr.response?.data?.detail || '创建失败')
    } finally {
      creating.value = false
    }
  }

  async function handleDelete(kbId: string) {
    try {
      await ElMessageBox.confirm('删除后该知识库下的所有文档将无法恢复，是否继续？', '确认删除', {
        type: 'warning',
      })
    } catch {
      return
    }

    try {
      await deleteKnowledgeBase(kbId)
      store.removeKnowledgeBase(kbId)
      ElMessage.success('知识库已删除')
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      ElMessage.error(axiosErr.response?.data?.detail || '删除失败')
    }
  }

  async function handleBuild(kbId: string) {
    try {
      await ElMessageBox.confirm(
        '重新构建会清空该知识库现有向量数据并重新切分，是否继续？',
        '确认重建',
        { type: 'warning' },
      )
    } catch {
      return
    }

    building.value = true
    try {
      const res = await buildKnowledgeBase(kbId)
      ElMessage.success(res.message)
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      ElMessage.error(axiosErr.response?.data?.detail || '重建失败')
    } finally {
      building.value = false
    }
  }

  async function handleUpload(kbId: string, file: File) {
    const suffix = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    const allowed = ['.txt', '.md', '.json', '.csv', '.pdf', '.docx', '.doc']
    if (!allowed.includes(suffix)) {
      ElMessage.warning(`仅支持 ${allowed.join(' / ')} 文件`)
      return
    }

    uploading.value = true
    try {
      const res = await uploadDocumentToKnowledgeBase(kbId, file)
      ElMessage.success(res.message)
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      ElMessage.error(axiosErr.response?.data?.detail || '上传失败')
    } finally {
      uploading.value = false
    }
  }

  function selectKb(kbId: string | null) {
    store.setCurrentKbId(kbId && kbId.trim() ? kbId : null)
  }

  onMounted(() => {
    void loadList()
    void loadKbTypes()
  })

  return {
    store,
    creating,
    building,
    uploading,
    kbTypes,
    loadList,
    handleCreate,
    handleDelete,
    handleBuild,
    handleUpload,
    selectKb,
  }
}
