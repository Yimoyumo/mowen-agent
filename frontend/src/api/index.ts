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
export { chatStream, askQuestion, askQuestionStream } from './chat'

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
