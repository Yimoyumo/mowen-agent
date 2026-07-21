"""对话历史路由。

提供对话会话和消息的 CRUD API，供前端同步使用。

路由：
- GET    /api/conversations                  列出所有会话（不含消息）
- GET    /api/conversations/{id}             获取单个会话（含全部消息）
- POST   /api/conversations                  创建新会话
- PUT    /api/conversations/{id}             更新会话（标题/kb）
- DELETE /api/conversations/{id}             删除会话
- DELETE /api/conversations                   清空所有会话
- POST   /api/conversations/{id}/messages     添加消息
- PUT    /api/conversations/{id}/messages/{msg_id}  更新消息
- DELETE /api/conversations/{id}/messages/{msg_id}  删除消息
- POST   /api/conversations/sync             批量同步（导入 localStorage）
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import NotFoundError, ValidationError
from server.core.conversation_store import conv_store
from server.core.logging_config import get_logger
from server.agent.checkpointer import get_checkpointer

import asyncio

logger = get_logger(__name__)
router = APIRouter()


async def _cleanup_checkpoint(thread_id: str) -> None:
    """删除指定 thread_id 的 LangGraph Checkpoint（防止 LLM 仍记得已删会话内容）。

    失败时只记录日志，不影响主流程（对话记录已删除，checkpoint 残留非致命）。
    """
    try:
        saver = await get_checkpointer()
        await saver.adelete_thread(thread_id)
        logger.info("Checkpoint 已删除: thread=%s", thread_id)
    except Exception as e:
        logger.warning("删除 Checkpoint 失败: thread=%s err=%s", thread_id, e)


# ==================== 请求模型 ====================

class CreateConversationRequest(BaseModel):
    id: str
    title: str = "新对话"
    kbId: str | None = None
    createdAt: int | None = None
    updatedAt: int | None = None


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    kbId: str | None = None


class AddMessageRequest(BaseModel):
    id: str
    role: str = "user"
    content: str = ""
    reasoning: str = ""
    contexts: list = []
    segments: list = []
    files: list = []
    createdAt: int | None = None


class UpdateMessageRequest(BaseModel):
    content: str | None = None
    reasoning: str | None = None
    contexts: list | None = None
    segments: list | None = None
    files: list | None = None


class BatchSyncRequest(BaseModel):
    conversations: list[dict]


# ==================== 会话路由 ====================

@router.get("/conversations")
async def list_conversations(since: int | None = None) -> dict:
    """列出所有会话（不含消息），按更新时间倒序。

    Args:
        since: 可选时间戳（毫秒），只返回 updated_at > since 的会话（增量同步）
    """
    convs = await asyncio.to_thread(conv_store.list_conversations, since)
    return {"conversations": convs, "total": len(convs)}


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    """获取单个会话及其所有消息。"""
    conv = conv_store.get_conversation(conv_id)
    if not conv:
        raise NotFoundError("会话不存在")
    return conv


@router.post("/conversations")
def create_conversation(req: CreateConversationRequest) -> dict:
    """创建新会话。"""
    conv = conv_store.create_conversation(
        req.id, req.title, req.kbId, req.createdAt, req.updatedAt
    )
    return conv


@router.put("/conversations/{conv_id}")
def update_conversation(conv_id: str, req: UpdateConversationRequest) -> dict:
    """更新会话标题或知识库。"""
    conv_store.update_conversation(conv_id, req.title, req.kbId)
    return {"status": "ok"}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str) -> dict:
    """删除会话及其所有消息 + 对应的 LangGraph Checkpoint。"""
    if not conv_store.delete_conversation(conv_id):
        raise NotFoundError("会话不存在")
    # 同步删除 Checkpointer 中该 thread 的状态（防止 LLM 仍记得已删会话内容）
    await _cleanup_checkpoint(conv_id)
    return {"status": "ok"}


@router.delete("/conversations")
async def delete_all_conversations() -> dict:
    """清空所有会话和消息 + 所有 LangGraph Checkpoint。"""
    # 先列出所有会话 ID（checkpoint 按 thread_id 删除）
    convs = conv_store.list_conversations()
    conv_store.delete_all()
    # 逐个删除 Checkpoint（失败不阻塞主流程）
    for conv in convs:
        await _cleanup_checkpoint(conv["id"])
    return {"status": "ok"}


# ==================== 消息路由 ====================

@router.post("/conversations/{conv_id}/messages")
def add_message(conv_id: str, req: AddMessageRequest) -> dict:
    """添加一条消息到指定会话。"""
    # 检查会话是否存在
    if not conv_store.get_conversation(conv_id):
        raise NotFoundError("会话不存在")

    msg = conv_store.add_message(conv_id, {
        "id": req.id,
        "role": req.role,
        "content": req.content,
        "reasoning": req.reasoning,
        "contexts": req.contexts,
        "segments": req.segments,
        "files": req.files,
        "createdAt": req.createdAt or 0,
    })
    return msg


@router.put("/conversations/{conv_id}/messages/{msg_id}")
def update_message(conv_id: str, msg_id: str, req: UpdateMessageRequest) -> dict:
    """更新消息的部分字段。"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not conv_store.update_message(conv_id, msg_id, updates):
        raise NotFoundError("消息不存在")
    return {"status": "ok"}


@router.delete("/conversations/{conv_id}/messages/{msg_id}")
def delete_message(conv_id: str, msg_id: str) -> dict:
    """删除单条消息。"""
    if not conv_store.delete_message(conv_id, msg_id):
        raise NotFoundError("消息不存在")
    return {"status": "ok"}


# ==================== 批量同步 ====================

@router.post("/conversations/sync")
async def batch_sync(req: BatchSyncRequest) -> dict:
    """批量同步：从前端 localStorage 导入所有会话和消息。

    策略：UPSERT（存在则更新，不存在则插入）。
    整个操作在单个事务中执行，放到线程池避免阻塞事件循环。
    """
    result = await asyncio.to_thread(conv_store.batch_sync, req.conversations)
    return result
