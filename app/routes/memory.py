"""记忆管理路由。

提供记忆的增删查改 API，供前端记忆管理页面使用。

路由：
- GET    /api/memories          获取所有记忆
- POST   /api/memories          手动添加记忆
- PUT    /api/memories/{id}     编辑记忆
- DELETE /api/memories/{id}     删除记忆
- DELETE /api/memories           清空所有记忆
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import NotFoundError, ValidationError
from server.agent.memory import memory_store
from server.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()


class MemoryItem(BaseModel):
    """单条记忆。"""
    type: str           # fact / preference / summary
    content: str        # 记忆内容


class MemoryResponse(BaseModel):
    """记忆列表响应。"""
    memories: list[dict]
    total: int


@router.get("/memories", response_model=MemoryResponse)
def list_memories() -> MemoryResponse:
    """获取所有记忆。"""
    memories = memory_store.get_all()
    return MemoryResponse(memories=memories, total=len(memories))


@router.post("/memories")
def add_memory(item: MemoryItem) -> dict:
    """手动添加一条记忆。

    type 可选值：fact（事实）、preference（偏好）、summary（摘要）
    """
    if not item.content.strip():
        raise ValidationError("记忆内容不能为空")

    if item.type not in ("fact", "preference", "summary"):
        raise ValidationError("记忆类型必须是 fact / preference / summary")

    mem_id = memory_store.add(item.type, item.content.strip())
    if mem_id is None:
        return {"status": "ok", "message": "记忆已存在（去重合并）", "id": None}
    return {"status": "ok", "message": "记忆已添加", "id": mem_id}


@router.put("/memories/{mem_id}")
def update_memory(mem_id: str, item: MemoryItem) -> dict:
    """编辑指定记忆。"""
    memories = memory_store.get_all()
    target = next((m for m in memories if m["id"] == mem_id), None)
    if target is None:
        raise NotFoundError("记忆不存在")

    if not item.content.strip():
        raise ValidationError("记忆内容不能为空")

    target["content"] = item.content.strip()
    if item.type in ("fact", "preference", "summary"):
        target["type"] = item.type

    memory_store.save(memories)
    logger.info("记忆已更新: %s", mem_id)
    return {"status": "ok", "message": "记忆已更新"}


@router.delete("/memories/{mem_id}")
def delete_memory(mem_id: str) -> dict:
    """删除指定记忆。"""
    if not memory_store.delete(mem_id):
        raise NotFoundError("记忆不存在")
    logger.info("记忆已删除: %s", mem_id)
    return {"status": "ok", "message": "记忆已删除"}


@router.delete("/memories")
def clear_memories() -> dict:
    """清空所有记忆。"""
    memory_store.clear()
    logger.info("所有记忆已清空")
    return {"status": "ok", "message": "所有记忆已清空"}
