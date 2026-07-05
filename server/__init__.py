"""墨问 AI 服务端。

目录结构：
    config.py              — RAGConfig 配置管理
    llm.py                 — LLM 厂商工厂
    embeddings.py          — Embedding 模型
    splitter.py            — 文档切分
    loader.py              — 文档加载
    knowledge_base.py      — 知识库管理
    vectorstore_chroma.py  — Chroma 向量库
    chain.py               — RAG 链（_resolve_collection_name 等工具函数）
    chat_chain.py          — 兼容层，重导出 agent.chat_stream
    retrieval/             — 检索模块
    agent/                 — Agent 模块
    legacy/                — 旧版 RAG（/ask 接口兼容）

公共 API：
    from server import chat_stream, get_agent_tools, RAGConfig
    from server.retrieval import expand_and_retrieve
    from server.agent import chat_stream
"""

from server.agent import chat_stream, get_agent_tools, set_agent_context
from server.retrieval import expand_and_retrieve, get_retriever, expand_query
from server.config import RAGConfig

__all__ = [
    "chat_stream",
    "get_agent_tools",
    "set_agent_context",
    "expand_and_retrieve",
    "get_retriever",
    "expand_query",
    "RAGConfig",
]
