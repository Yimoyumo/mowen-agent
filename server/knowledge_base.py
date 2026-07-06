"""知识库管理模块。

提供知识库的 CRUD、元数据持久化，以及与 Chroma collection 的映射。

持久化方式：SQLite 数据库（server/db.py）
旧数据迁移：首次启动时自动从 knowledge_bases.json 导入。
"""

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from server.config import RAGConfig
from server.db import db
from server.logging_config import get_logger

logger = get_logger(__name__)


# 知识库类型映射：key → 中文标签
KB_TYPES = {
    "novel": "小说",
    "tech": "技术文档",
    "project": "项目文档",
    "general": "通用文档",
}

DEFAULT_KB_TYPE = "general"


@dataclass
class KnowledgeBase:
    """知识库元数据。

    存储在 SQLite knowledge_bases 表中，与 Chroma collection 一一对应。
    """

    id: str               # UUID 唯一标识
    name: str            # 用户可见的名称
    description: str     # 描述
    created_at: str      # 创建时间（ISO 格式）
    collection_name: str # Chroma collection 名称（由 id 派生）
    kb_type: str = DEFAULT_KB_TYPE  # novel/tech/project/general


def _sanitize_collection_name(kb_id: str) -> str:
    """Chroma collection 名称只允许字母数字下划线连字符。"""
    return f"kb_{kb_id.replace('-', '_')}"


def load_knowledge_bases(config: RAGConfig | None = None) -> list[KnowledgeBase]:
    """加载所有知识库元数据。"""
    rows = db.execute("SELECT * FROM knowledge_bases ORDER BY created_at").fetchall()
    return [
        KnowledgeBase(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            collection_name=row["collection_name"],
            kb_type=row["kb_type"],
        )
        for row in rows
    ]


def create_knowledge_base(
    name: str,
    description: str = "",
    kb_type: str = DEFAULT_KB_TYPE,
    config: RAGConfig | None = None,
) -> KnowledgeBase:
    """创建新知识库。"""
    kb_type = (kb_type or DEFAULT_KB_TYPE).strip().lower()
    if kb_type not in KB_TYPES:
        kb_type = DEFAULT_KB_TYPE

    kb_id = str(uuid.uuid4())
    kb = KnowledgeBase(
        id=kb_id,
        name=name,
        description=description,
        created_at=datetime.now().isoformat(),
        collection_name=_sanitize_collection_name(kb_id),
        kb_type=kb_type,
    )

    db.execute(
        """INSERT INTO knowledge_bases
           (id, name, description, kb_type, collection_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (kb.id, kb.name, kb.description, kb.kb_type, kb.collection_name, kb.created_at),
    )
    db.commit()

    logger.info("知识库已创建: %s (%s)", kb.name, kb.id)
    return kb


def get_knowledge_base(
    kb_id: str,
    config: RAGConfig | None = None,
) -> KnowledgeBase | None:
    """根据 ID 获取知识库。"""
    row = db.execute(
        "SELECT * FROM knowledge_bases WHERE id = ?",
        (kb_id,),
    ).fetchone()

    if row is None:
        return None

    return KnowledgeBase(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        collection_name=row["collection_name"],
        kb_type=row["kb_type"],
    )


def delete_knowledge_base(kb_id: str, config: RAGConfig | None = None) -> bool:
    """删除知识库及其 Chroma collection。"""
    kb = get_knowledge_base(kb_id, config)
    if kb is None:
        return False

    # 删除数据库记录
    db.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    db.commit()

    # 删除 collection 持久化目录
    config = config or RAGConfig.from_settings()
    collection_dir = Path(config.vector_store_dir) / "chroma" / kb.collection_name
    if collection_dir.exists():
        shutil.rmtree(collection_dir, ignore_errors=True)

    logger.info("知识库已删除: %s (%s)", kb.name, kb.id)
    return True


def ensure_default_knowledge_base(config: RAGConfig | None = None) -> KnowledgeBase:
    """确保至少存在一个默认知识库，用于兼容旧数据。"""
    kbs = load_knowledge_bases(config)
    if kbs:
        return kbs[0]

    return create_knowledge_base("默认知识库", "系统自动创建的默认知识库")


def get_kb_type_label(kb_type: str) -> str:
    """获取知识库类型的可读标签。"""
    return KB_TYPES.get(kb_type, KB_TYPES[DEFAULT_KB_TYPE])
