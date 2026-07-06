"""对话相关路由：通用对话 + 旧版 RAG 问答。"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.errors import InternalError, ValidationError
from app.models import AskRequest, AskResponse, ChatRequest
from server.logging_config import get_logger

from server.chat_chain import chat_stream as rag_chat_stream  # 通用对话链（多轮 + 可选 RAG）
from server.legacy.pipeline import ask, ask_stream                     # 旧版 RAG 问答

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """通用对话流式接口（可选 RAG 增强）。"""
    # 参数校验
    if not request.messages:
        raise ValidationError("消息不能为空")

    last_msg = request.messages[-1]
    if not last_msg.get("content", "").strip():
        raise ValidationError("问题不能为空")

    # SSE 流式生成器：逐块调用 rag_chat_stream 并以 data: 格式输出
    async def event_generator():
        try:
            async for chunk in rag_chat_stream(
                request.messages, request.kb_id,
                stream=request.stream,
                show_reasoning=request.show_reasoning,
                uploaded_files=request.uploaded_files or [],
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("对话流异常: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': '对话处理出错，请重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",          # 禁用缓存，确保实时输出
            "Connection": "keep-alive",            # 保持长连接
            "X-Accel-Buffering": "no",             # 禁止 Nginx 缓冲（确保流式即时推送）
        },
    )


# ==================== 旧版 RAG 问答接口（保留兼容） ====================


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest) -> AskResponse:
    """RAG 问答接口（非流式，一次性返回完整结果）。"""
    if not request.question.strip():
        raise ValidationError("问题不能为空")

    if not request.kb_id:
        raise ValidationError("请先选择一个知识库")

    try:
        result = ask(request.question, request.kb_id)
    except Exception as exc:
        raise InternalError("问答失败", detail=str(exc)) from exc

    return AskResponse(
        question=result["input"],
        answer=result["answer"],
        contexts=[doc.page_content for doc in result["context"]],
    )


@router.post("/ask/stream")
def ask_stream_endpoint(request: AskRequest) -> StreamingResponse:
    """流式 RAG 问答接口（先返回上下文，再逐 token 输出回答）。"""
    if not request.question.strip():
        raise ValidationError("问题不能为空")

    if not request.kb_id:
        raise ValidationError("请先选择一个知识库")

    async def event_generator():
        try:
            async for chunk in ask_stream(request.question, request.kb_id):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("RAG 流式问答异常: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': '问答处理出错，请重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
