"""知识库管理模块。

提供知识库的 CRUD、元数据持久化，以及与 Chroma collection 的映射。
"""

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from server.config import RAGConfig


KB_META_FILE = "knowledge_bases.json"   # 知识库元数据持久化文件名


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

    存储在 knowledge_bases.json 中，与 Chroma collection 一一对应。
    """

    id: str               # UUID 唯一标识
    name: str            # 用户可见的名称
    description: str     # 描述
    created_at: str      # 创建时间（ISO 格式）
    collection_name: str # Chroma collection 名称（由 id 派生）
    kb_type: str = DEFAULT_KB_TYPE  # novel/tech/project/general


def _get_meta_path(config: RAGConfig | None = None) -> Path:
    config = config or RAGConfig.from_json()
    base_dir = Path(config.vector_store_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / KB_META_FILE


def _sanitize_collection_name(kb_id: str) -> str:
    """Chroma collection 名称只允许字母数字下划线连字符。"""
    return f"kb_{kb_id.replace('-', '_')}"


def load_knowledge_bases(config: RAGConfig | None = None) -> list[KnowledgeBase]:
    """加载所有知识库元数据。"""
    meta_path = _get_meta_path(config)
    if not meta_path.exists():
        return []

    with open(meta_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return [KnowledgeBase(**item) for item in raw]


def save_knowledge_bases(kbs: list[KnowledgeBase], config: RAGConfig | None = None) -> None:
    """保存所有知识库元数据。"""
    meta_path = _get_meta_path(config)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump([asdict(kb) for kb in kbs], f, ensure_ascii=False, indent=2)


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

    kbs = load_knowledge_bases(config)

    kb_id = str(uuid.uuid4())
    kb = KnowledgeBase(
        id=kb_id,
        name=name,
        description=description,
        created_at=datetime.now().isoformat(),
        collection_name=_sanitize_collection_name(kb_id),
        kb_type=kb_type,
    )

    kbs.append(kb)
    save_knowledge_bases(kbs, config)
    return kb


def get_knowledge_base(
    kb_id: str,
    config: RAGConfig | None = None,
) -> KnowledgeBase | None:
    """根据 ID 获取知识库。"""
    for kb in load_knowledge_bases(config):
        if kb.id == kb_id:
            return kb
    return None


def delete_knowledge_base(kb_id: str, config: RAGConfig | None = None) -> bool:
    """删除知识库及其 Chroma collection。"""
    kbs = load_knowledge_bases(config)
    target = next((kb for kb in kbs if kb.id == kb_id), None)
    if target is None:
        return False

    kbs.remove(target)
    save_knowledge_bases(kbs, config)

    # 删除 collection 持久化目录
    config = config or RAGConfig.from_json()
    collection_dir = Path(config.vector_store_dir) / "chroma" / target.collection_name
    if collection_dir.exists():
        shutil.rmtree(collection_dir, ignore_errors=True)

    return True


def ensure_default_knowledge_base(config: RAGConfig | None = None) -> KnowledgeBase:
    """确保至少存在一个默认知识库，用于兼容旧数据。"""
    kbs = load_knowledge_bases(config)
    if kbs:
        return kbs[0]

    return create_knowledge_base("默认知识库", "系统自动创建的默认知识库", config)


def get_kb_type_label(kb_type: str) -> str:
    """获取知识库类型的可读标签。"""
    return KB_TYPES.get(kb_type, KB_TYPES[DEFAULT_KB_TYPE])
