"""Chroma 向量存储模块。

提供 Chroma 向量库的创建、加载、追加功能。
每个知识库对应一个独立的 Chroma collection，持久化到本地目录。
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from server.core.config import RAGConfig
from server.llm.embeddings import get_embeddings


def _get_collection_persist_dir(
    collection_name: str,
    config: RAGConfig | None = None,
) -> Path:
    """获取 collection 的持久化目录路径，不存在则创建。"""
    config = config or RAGConfig.from_settings()
    persist_dir = Path(config.vector_store_dir) / "chroma" / collection_name
    persist_dir.mkdir(parents=True, exist_ok=True)
    return persist_dir


def create_vector_store(
    documents: list[Document],
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> Chroma:
    """从文档列表创建 Chroma 向量库。

    智谱 Embedding API 单次最多支持 64 条文本，因此分批次添加。
    """
    config = config or RAGConfig.from_settings()
    embeddings = get_embeddings(config)
    persist_dir = _get_collection_persist_dir(collection_name, config)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    # 分批添加，每批最多 64 条（智谱 API 限制）
    batch_size = 64
    total = len(documents)
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vector_store.add_documents(batch)

    return vector_store


def load_vector_store(
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> Chroma:
    """从本地目录加载 Chroma 向量库。

    若 collection 尚未写入数据，也返回 Chroma 实例（空库），避免调用方报错。
    """
    config = config or RAGConfig.from_settings()
    persist_dir = _get_collection_persist_dir(collection_name, config)

    embeddings = get_embeddings(config)
    return Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )


def append_to_vector_store(
    documents: list[Document],
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> Chroma:
    """向已有 Chroma 向量库追加文档（不删除原有数据）。"""
    config = config or RAGConfig.from_settings()
    embeddings = get_embeddings(config)
    persist_dir = _get_collection_persist_dir(collection_name, config)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    # 分批添加，每批最多 64 条（智谱 API 限制）
    batch_size = 64
    total = len(documents)
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vector_store.add_documents(batch)

    return vector_store
