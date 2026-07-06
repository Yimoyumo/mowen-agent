"""旧版 RAG 检索-生成链模块。

组合查询扩写、多查询检索、提示模板和大模型，构建完整的问答链。
新版通用对话使用 rag/chat_chain.py，此模块保留供 /ask 接口兼容。

提示词统一管理在 server/prompts/rag.py 中。
"""

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables import RunnablePassthrough

from server.config import RAGConfig
from server.llm import get_chat_model
from server.prompts import RAG_CHAT_PROMPT
from server.retrieval import expand_and_retrieve


def get_rag_chain(kb_id: str | None = None, config: RAGConfig | None = None):
    """构建带查询扩写的 RAG 检索生成链。

    Args:
        kb_id: 知识库 ID，为空时使用默认知识库。
        config: RAG 配置。

    Returns:
        调用 invoke({"input": question}) 后返回 {"input", "context", "answer"} 字典。
    """
    config = config or RAGConfig.from_settings()
    llm = get_chat_model(config)
    collection_name = _resolve_collection_name(kb_id, config)

    question_answer_chain = create_stuff_documents_chain(llm, RAG_CHAT_PROMPT)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config)
        )
        | RunnablePassthrough.assign(answer=question_answer_chain)
    )


def get_rag_streaming_chain(kb_id: str | None = None, config: RAGConfig | None = None):
    """构建可流式输出的 RAG 链。

    与 get_rag_chain 类似，但 answer 字段直接绑定 LLM 的流式输出（异步迭代器）。
    """
    config = config or RAGConfig.from_settings()
    llm = get_chat_model(config)
    collection_name = _resolve_collection_name(kb_id, config)

    async def generate_answer(x: dict) -> object:
        formatted_messages = RAG_CHAT_PROMPT.format_messages(context=x["context"], input=x["input"])
        return llm.astream(formatted_messages)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config)
        )
        | RunnablePassthrough.assign(answer=generate_answer)
    )


def _resolve_collection_name(kb_id: str | None, config: RAGConfig | None = None) -> str:
    """将知识库 ID 解析为 Chroma collection 名称。"""
    if not kb_id:
        return "default"

    from server.knowledge_base import get_knowledge_base

    kb = get_knowledge_base(kb_id, config)
    return kb.collection_name if kb else "default"
