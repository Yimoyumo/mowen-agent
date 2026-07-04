"""向量存储模块。

基于 FAISS 构建本地向量库，支持创建、保存、加载和检索。
"""

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from rag.config import RAGConfig
from rag.embeddings import get_embeddings


def create_vector_store(
    documents: list[Document],
    config: RAGConfig | None = None,
) -> FAISS:
    """从文档列表创建 FAISS 向量库。"""
    config = config or RAGConfig.from_json()
    embeddings = get_embeddings(config)
    return FAISS.from_documents(documents, embeddings)


def save_vector_store(vector_store: FAISS, config: RAGConfig | None = None) -> None:
    """保存向量库到本地目录。"""
    config = config or RAGConfig.from_json()
    save_path = Path(config.vector_store_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(save_path))


def load_vector_store(config: RAGConfig | None = None) -> FAISS:
    """从本地目录加载向量库。"""
    config = config or RAGConfig.from_json()
    load_path = Path(config.vector_store_dir)
    if not load_path.exists():
        raise FileNotFoundError(f"向量库目录不存在: {load_path.absolute()}")

    embeddings = get_embeddings(config)
    return FAISS.load_local(
        str(load_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )
