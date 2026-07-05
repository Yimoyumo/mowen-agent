"""Agent 工具集。

定义可供 Agent 调用的工具函数：
- search_knowledge_base: 检索上传的知识库文档
- search_web: 联网搜索实时信息
"""

import contextvars

from langchain_core.tools import tool
from tavily import TavilyClient

from server.config import RAGConfig
from server.retrieval.retriever import expand_and_retrieve
from server.chain import _resolve_collection_name

# 通过 contextvar 将 kb_id 和 config 从 chat_stream 传入工具
_current_kb_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "kb_id", default=None
)
_current_config: contextvars.ContextVar[RAGConfig] = contextvars.ContextVar(
    "config"
)


def set_agent_context(kb_id: str | None, config: RAGConfig) -> None:
    """设置 Agent 工具的运行时上下文（由 chat_stream 调用）。"""
    _current_kb_id.set(kb_id)
    _current_config.set(config)


@tool
def search_knowledge_base(query: str) -> str:
    """在用户已上传的知识库中搜索相关内容，返回最相关的文档片段。
    适用场景：用户询问文档、小说、技术手册、项目资料等知识库内的问题。
    不适用场景：实时新闻、天气、股价等动态信息——这类问题请用 search_web。"""
    config = _current_config.get()
    kb_id = _current_kb_id.get()

    if not kb_id:
        return "（当前未选择知识库，无法检索。请告诉用户需要先选择一个知识库。）"

    collection_name = _resolve_collection_name(kb_id, config)
    docs = expand_and_retrieve(query, collection_name, config)

    if not docs:
        return "（知识库中未找到相关内容）"

    return "\n\n---\n\n".join(
        f"【来源 {i + 1}】{doc.page_content}"
        for i, doc in enumerate(docs)
    )


@tool
def search_web(query: str) -> str:
    """搜索互联网获取实时信息，返回搜索结果摘要。
    适用场景：最新新闻、天气、股价、实时事件等知识库无法覆盖的动态信息。
    不适用场景：已上传知识库中的内容——这类问题请用 search_knowledge_base。"""
    config = _current_config.get()

    if not config.tavily_api_key:
        return "（联网搜索功能未配置 API Key，请联系管理员设置 tavily_api_key）"

    try:
        client = TavilyClient(api_key=config.tavily_api_key)
        result = client.search(query, search_depth="basic", max_results=5)
    except Exception as exc:
        return f"（搜索失败: {exc}）"

    if not result.get("results"):
        return "（未找到相关搜索结果）"

    return "\n\n".join(
        f"【{r['title']}】({r['url']})\n{r['content']}"
        for r in result["results"]
    )


def get_agent_tools() -> list:
    """获取 Agent 可用工具列表。"""
    return [search_knowledge_base, search_web]
