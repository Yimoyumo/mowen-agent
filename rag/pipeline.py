"""RAG 完整流程封装。

提供从原始文档构建向量库、到执行问答的一站式接口。
这是旧版 RAG 链的入口，新版通用对话使用 rag/chat_chain.py。
"""

from pathlib import Path

from langchain_core.documents import Document

from rag.config import RAGConfig
from rag.knowledge_base import get_knowledge_base
from rag.loader import load_directory
from rag.splitter import split_documents_by_type
from rag.vectorstore_chroma import create_vector_store, append_to_vector_store
from rag.chain import get_rag_chain, get_rag_streaming_chain


def _resolve_kb_type(kb_id: str | None, config: RAGConfig | None = None) -> str:
    """根据知识库 ID 解析知识库类型。"""
    if not kb_id:
        return "general"
    kb = get_knowledge_base(kb_id, config)
    return kb.kb_type if kb else "general"


def build_vector_store_from_directory(
    dir_path: str | Path,
    collection_name: str = "default",
    kb_type: str = "general",
    config: RAGConfig | None = None,
) -> None:
    """从文档目录构建并保存向量库。"""
    config = config or RAGConfig.from_json()
    print(f"正在加载文档: {dir_path}")
    documents = load_directory(dir_path)
    print(f"共加载 {len(documents)} 个文件")

    build_vector_store_from_documents(documents, collection_name, kb_type, config)


def build_vector_store_from_documents(
    documents: list[Document],
    collection_name: str = "default",
    kb_type: str = "general",
    config: RAGConfig | None = None,
) -> None:
    """从文档对象列表构建并保存向量库。"""
    config = config or RAGConfig.from_json()

    print(f"正在按 [{kb_type}] 策略切分文档...")
    chunks = split_documents_by_type(documents, kb_type, config)
    print(f"切分为 {len(chunks)} 个文本块")

    print("正在构建 Chroma 向量库...")
    vector_store = create_vector_store(chunks, collection_name, config)
    print(f"Chroma 向量库已持久化到: {config.vector_store_dir}/chroma/{collection_name}")
    print("向量库构建完成")


def append_documents_to_knowledge_base(
    documents: list[Document],
    collection_name: str = "default",
    kb_type: str = "general",
    config: RAGConfig | None = None,
) -> None:
    """向指定知识库追加文档。"""
    config = config or RAGConfig.from_json()

    print(f"正在按 [{kb_type}] 策略切分追加文档...")
    chunks = split_documents_by_type(documents, kb_type, config)
    print(f"切分为 {len(chunks)} 个文本块")

    print("正在追加到 Chroma 向量库...")
    append_to_vector_store(chunks, collection_name, config)
    print(f"Chroma 向量库已更新: {config.vector_store_dir}/chroma/{collection_name}")


def ask(question: str, kb_id: str | None = None, config: RAGConfig | None = None) -> dict:
    """执行一次 RAG 问答。"""
    chain = get_rag_chain(kb_id, config)
    return chain.invoke({"input": question})


async def ask_stream(question: str, kb_id: str | None = None, config: RAGConfig | None = None):
    """流式执行一次 RAG 问答。

    Yields:
        字典序列：
        - {"type": "question", "question": "..."}
        - {"type": "contexts", "contexts": ["..."]}
        - {"type": "token", "token": "..."}
        - {"type": "done"}
    """
    config = config or RAGConfig.from_json()
    chain = get_rag_streaming_chain(kb_id, config)

    result = await chain.ainvoke({"input": question})
    contexts: list[Document] = result["context"]
    context_texts = [doc.page_content for doc in contexts]

    yield {"type": "question", "question": question}
    yield {"type": "contexts", "contexts": context_texts}

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

