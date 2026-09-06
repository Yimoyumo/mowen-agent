"""人机交互路由：审批卡片 / 主动提问的应答与查询。

- GET  /api/interactions/pending → 列出待处理的交互请求
- POST /api/interactions/{request_id}/answer → 应答一个交互请求（审批/回答）
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import NotFoundError, ValidationError
from server.agent import interaction
from server.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()


class AnswerRequest(BaseModel):
    """应答请求体。"""

    approved: bool | None = None
    scope: str = "once"          # once / session / always
    answer: str | None = None


@router.get("/interactions/pending")
def pending_interactions(session_id: str | None = None) -> dict:
    """列出待处理的交互请求（可按 session_id 过滤）。

    响应键与前端契约一致：{"requests": [...]}；保留 "pending" 旧键兼容。
    """
    items = interaction.pending(session_id)
    return {"requests": items, "pending": items}


@router.post("/interactions/{request_id}/answer")
def answer_interaction(request_id: str, body: AnswerRequest) -> dict:
    """应答一个交互请求。

    - approval 场景：approdved=True/False 决定是否放行，scope 决定审批作用域。
    - ask_user 场景：answer 为用户回答文本。

    请求不存在或已过期时返回 404。
    """
    if body.scope not in ("once", "session", "always"):
        raise ValidationError(f"scope 必须为 once/session/always，收到: {body.scope}")

    ok = interaction.answer(
        request_id,
        approved=body.approved,
        scope=body.scope,
        answer=body.answer,
    )
    if not ok:
        raise NotFoundError("交互请求")
    return {"ok": True, "request_id": request_id}
