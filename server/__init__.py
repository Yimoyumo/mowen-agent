"""墨问 AI 服务端。

目录结构：
    core/                  - 基础设施（config/db/logging/user_settings/conversation_store）
    llm/                   - LLM 抽象（factory/embeddings/provider_config/model_context）
    rag/                   - RAG 管线（loader/splitter/vectorstore/knowledge_base/chain）
    retrieval/             - 检索模块
    agent/                 - Agent 模块（graph/tools/sandbox/mcp/memory/skills）
    prompts/               - 提示词模板

公共 API：
    from server import chat_stream, get_agent_tools, RAGConfig
    from server.retrieval import expand_and_retrieve
    from server.agent import chat_stream
"""

from server.agent import chat_stream, get_agent_tools, set_agent_context
from server.retrieval import expand_and_retrieve, get_retriever, expand_query
from server.core.config import RAGConfig

__all__ = [
    "chat_stream",
    "get_agent_tools",
    "set_agent_context",
    "expand_and_retrieve",
    "get_retriever",
    "expand_query",
    "RAGConfig",
]
