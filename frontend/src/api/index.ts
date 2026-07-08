/** API 统一导出 */

export { apiClient, API_BASE_URL } from './config'
export { healthCheck, getConfig } from './configApi'
export {
  getKnowledgeBases,
  getKnowledgeBaseTypes,
  createKnowledgeBase,
  deleteKnowledgeBase,
  buildKnowledgeBase,
  getKnowledgeBaseDocuments,
  uploadDocumentToKnowledgeBase,
} from './knowledgeBaseApi'
export { chatStream } from './chat'

// 用户设置
export {
  getSettings,
  updateSettings,
  resetSettings,
  getProviders,
  updateProvider,
  addCustomProvider,
  deleteCustomProvider,
  fetchProviderModels,
  setCurrentModel,
  getProfile,
  updateProfile,
  getMemories,
  addMemory,
  updateMemory,
  deleteMemory,
  clearMemories,
} from './settingsApi'

// 对话历史
export {
  listConversations,
  getConversation,
  createConversation,
  updateConversation,
  deleteConversation,
  deleteAllConversations,
  addMessage as apiAddMessage,
  updateMessage as apiUpdateMessage,
  deleteMessage as apiDeleteMessage,
  syncConversations,
} from './conversations'

// 定时任务
export {
  listScheduledTasks,
  getScheduledTask,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  pauseScheduledTask,
  resumeScheduledTask,
  runScheduledTaskNow,
  getScheduledTaskConversation,
} from './scheduledTaskApi'
