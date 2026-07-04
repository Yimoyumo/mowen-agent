"""Chroma 向量存储模块。

提供与 FAISS 平行的 Chroma 向量库实现，支持自动持久化。
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.config import RAGConfig
from rag.embeddings import get_embeddings


def _get_collection_persist_dir(
    collection_name: str,
    config: RAGConfig | None = None,
) -> Path:
    config = config or RAGConfig.from_json()
    persist_dir = Path(config.vector_store_dir) / "chroma" / collection_name
    persist_dir.mkdir(parents=True, exist_ok=True)
    return persist_dir


def create_vector_store(
    documents: list[Document],
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> Chroma:
    """从文档列表创建 Chroma 向量库。"""
    config = config or RAGConfig.from_json()
    embeddings = get_embeddings(config)
    persist_dir = _get_collection_persist_dir(collection_name, config)

    # 智谱 Embedding API 单次最多支持 64 条文本，分批次添加
    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )
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
    config = config or RAGConfig.from_json()
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
    """向已有 Chroma 向量库追加文档。"""
    config = config or RAGConfig.from_json()
    embeddings = get_embeddings(config)
    persist_dir = _get_collection_persist_dir(collection_name, config)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    batch_size = 64
    total = len(documents)
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vector_store.add_documents(batch)

    return vector_store
