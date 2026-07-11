"""RAG 检索-生成链与向量库构建。

组合查询扩写、多查询检索、提示模板和大模型，构建完整的问答链。
同时提供向量库构建函数（供知识库路由调用）。

提示词统一管理在 server/prompts/rag.py 中。
"""

from pathlib import Path

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough

from server.core.config import RAGConfig
from server.rag.knowledge_base import get_knowledge_base
from server.rag.loader import load_directory
from server.core.logging_config import get_logger
from server.llm.factory import get_chat_model
from server.prompts import RAG_CHAT_PROMPT
from server.retrieval import expand_and_retrieve
from server.rag.splitter import split_documents_by_type
from server.rag.vectorstore import (
    append_to_vector_store,
    create_vector_store,
)

logger = get_logger(__name__)


# ==================== 集合名解析 ====================

def _resolve_collection_name(kb_id: str | None, config: RAGConfig | None = None) -> str:
    """将知识库 ID 解析为 Chroma collection 名称。"""
    if not kb_id:
        return "default"

    kb = get_knowledge_base(kb_id, config)
    return kb.collection_name if kb else "default"


def _resolve_kb_type(kb_id: str | None, config: RAGConfig | None = None) -> str:
    """将知识库 ID 解析为知识库类型。"""
    if not kb_id:
        return "general"

    kb = get_knowledge_base(kb_id, config)
    return kb.kb_type if kb else "general"


# ==================== RAG 链构建 ====================

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
    kb_type = _resolve_kb_type(kb_id, config)

    question_answer_chain = create_stuff_documents_chain(llm, RAG_CHAT_PROMPT)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config, kb_type)
        )
        | RunnablePassthrough.assign(
            context=lambda x: x["context"]
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
    kb_type = _resolve_kb_type(kb_id, config)

    async def generate_answer(x: dict) -> object:
        formatted_messages = RAG_CHAT_PROMPT.format_messages(context=x["context"], input=x["input"])
        return llm.astream(formatted_messages)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config, kb_type)
        )
        | RunnablePassthrough.assign(
            context=lambda x: x["context"]
        )
        | RunnablePassthrough.assign(answer=generate_answer)
    )


# ==================== RAG 问答 ====================

def ask(question: str, kb_id: str | None = None, config: RAGConfig | None = None) -> dict:
    """执行一次 RAG 问答（非流式）。"""
    chain = get_rag_chain(kb_id, config)
    return chain.invoke({"input": question})


async def ask_stream(question: str, kb_id: str | None = None, config: RAGConfig | None = None):
    """流式执行 RAG 问答。

    Yields:
        {"type": "question", ...} -> {"type": "contexts", ...} -> {"type": "token", ...} -> {"type": "done"}
    """
    config = config or RAGConfig.from_settings()
    chain = get_rag_streaming_chain(kb_id, config)

    result = await chain.ainvoke({"input": question})
    contexts: list[Document] = result["context"]

    yield {"type": "question", "question": question}
    yield {"type": "contexts", "contexts": [d.page_content for d in contexts]}

    answer_stream = result["answer"]
    async for token in answer_stream:
        content = _extract_token_content(token)
        if content:
            yield {"type": "token", "token": content}

    yield {"type": "done"}


def _extract_token_content(token) -> str:
    """从流式 Token 中提取文本内容。

    DeepSeek 部分模型（尤其是带思考能力的版本）会把生成内容放到
    additional_kwargs['reasoning_content'] 中，需要同时提取 content
    和 reasoning_content。
    """
    if isinstance(token, str):
        return token

    parts: list[str] = []
    if hasattr(token, "content") and token.content:
        parts.append(str(token.content))

    reasoning = getattr(token, "additional_kwargs", {}).get("reasoning_content", "")
    if reasoning:
        parts.append(str(reasoning))

    return "".join(parts)


# ==================== 向量库构建 ====================

def build_vector_store_from_directory(
    dir_path: str | Path,
    collection_name: str = "default",
    kb_type: str = "general",
    kb_id: str | None = None,
    config: RAGConfig | None = None,
) -> None:
    """从文档目录构建并保存向量库。"""
    config = config or RAGConfig.from_settings()
    logger.info("正在加载文档: %s", dir_path)
    documents = load_directory(dir_path)
    logger.info("共加载 %d 个文件", len(documents))

    build_vector_store_from_documents(documents, collection_name, kb_type, kb_id, config)


def build_vector_store_from_documents(
    documents: list[Document],
    collection_name: str = "default",
    kb_type: str = "general",
    kb_id: str | None = None,
    config: RAGConfig | None = None,
) -> None:
    """从文档对象列表构建并保存向量库。"""
    config = config or RAGConfig.from_settings()

    logger.info("正在按 [%s] 策略切分文档...", kb_type)
    chunks = split_documents_by_type(documents, kb_type, config)
    logger.info("切分为 %d 个文本块", len(chunks))

    logger.info("正在构建 Chroma 向量库...")
    create_vector_store(chunks, collection_name, config, kb_id=kb_id)
    logger.info("向量库构建完成: %s/chroma/%s", config.vector_store_dir, collection_name)


def append_documents_to_knowledge_base(
    documents: list[Document],
    collection_name: str = "default",
    kb_type: str = "general",
    config: RAGConfig | None = None,
) -> None:
    """向指定知识库追加文档。"""
    config = config or RAGConfig.from_settings()

    logger.info("正在按 [%s] 策略切分追加文档...", kb_type)
    chunks = split_documents_by_type(documents, kb_type, config)
    logger.info("切分为 %d 个文本块", len(chunks))

    logger.info("正在追加到 Chroma 向量库...")
    append_to_vector_store(chunks, collection_name, config)
    logger.info("向量库已更新: %s/chroma/%s", config.vector_store_dir, collection_name)
