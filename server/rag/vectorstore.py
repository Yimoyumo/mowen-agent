"""Chroma 向量存储模块。

提供 Chroma 向量库的创建、加载、追加功能。
每个知识库对应一个独立的 Chroma collection，持久化到本地目录。

维度管理：
- 创建时自动检测 embedding 维度并存入 DB
- 加载/追加时校验当前 embedding 模型维度是否与 collection 一致
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from server.core.config import RAGConfig
from server.core.logging_config import get_logger
from server.llm.embeddings import get_embeddings, get_embedding_dim

logger = get_logger(__name__)


def _get_collection_persist_dir(
    collection_name: str,
    config: RAGConfig | None = None,
) -> Path:
    """获取 collection 的持久化目录路径，不存在则创建。"""
    config = config or RAGConfig.from_settings()
    persist_dir = Path(config.vector_store_dir) / "chroma" / collection_name
    persist_dir.mkdir(parents=True, exist_ok=True)
    return persist_dir


def _check_dimension_mismatch(
    collection_name: str,
    embeddings,
    config: RAGConfig,
) -> None:
    """检查当前 embedding 模型维度与 collection 已有的维度是否一致。

    不一致时抛出 ValueError，包含切换模型的提示。
    """
    from server.rag.knowledge_base import load_knowledge_bases

    kbs = load_knowledge_bases(config)
    kb = next((k for k in kbs if k.collection_name == collection_name), None)
    if kb is None or kb.embedding_dim <= 0:
        return  # 新 collection 或旧数据无维度记录，跳过

    current_dim = get_embedding_dim(embeddings)
    if current_dim <= 0:
        return  # 无法检测，跳过

    if current_dim != kb.embedding_dim:
        raise ValueError(
            f"向量维度不匹配！\n"
            f"  知识库 \"{kb.name}\" 创建时使用 {kb.embedding_model}（{kb.embedding_dim}维）\n"
            f"  当前 embedding 模型输出 {current_dim}维\n"
            f"  请切换回 {kb.embedding_model} 或重建知识库。"
        )


def _get_batch_size(documents: list[Document]) -> int:
    """返回批大小。"""
    return 64


def create_vector_store(
    documents: list[Document],
    collection_name: str = "default",
    config: RAGConfig | None = None,
    kb_id: str | None = None,
) -> Chroma:
    """从文档列表创建 Chroma 向量库。

    创建完成后自动检测 embedding 维度并记录到 DB。
    """
    config = config or RAGConfig.from_settings()
    embeddings = get_embeddings(config)
    persist_dir = _get_collection_persist_dir(collection_name, config)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    # 分批添加
    batch_size = _get_batch_size(documents)
    total = len(documents)
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vector_store.add_documents(batch)

    # 检测维度并记录到 DB
    dim = get_embedding_dim(embeddings)
    if dim > 0 and kb_id:
        from server.rag.knowledge_base import update_knowledge_base_embedding
        model_id = config.embedding_model or _resolve_model_name(config)
        update_knowledge_base_embedding(kb_id, model_id, dim)
        logger.info("知识库 %s embedding: %s (%d维)", collection_name, model_id, dim)

    return vector_store


def load_vector_store(
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> Chroma:
    """从本地目录加载 Chroma 向量库。

    若 collection 尚未写入数据，也返回 Chroma 实例（空库），避免调用方报错。
    加载时校验 embedding 维度是否匹配已有数据。
    """
    config = config or RAGConfig.from_settings()
    persist_dir = _get_collection_persist_dir(collection_name, config)
    embeddings = get_embeddings(config)

    _check_dimension_mismatch(collection_name, embeddings, config)

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

    _check_dimension_mismatch(collection_name, embeddings, config)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=collection_name,
    )

    # 分批添加
    batch_size = _get_batch_size(documents)
    total = len(documents)
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vector_store.add_documents(batch)

    return vector_store


def _resolve_model_name(config: RAGConfig) -> str:
    """从配置解析当前使用的 embedding 模型名称。"""
    from server.llm.embeddings import resolve_embedding
    try:
        provider, model, _ = resolve_embedding(config)
        return f"{provider}/{model}"
    except ValueError:
        return "unknown"
