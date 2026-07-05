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
