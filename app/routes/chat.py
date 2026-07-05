"""对话相关路由：通用对话 + 旧版 RAG 问答。"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import AskRequest, AskResponse, ChatRequest

from server.chat_chain import chat_stream as rag_chat_stream  # 通用对话链（多轮 + 可选 RAG）
from server.legacy.pipeline import ask, ask_stream                     # 旧版 RAG 问答

router = APIRouter()


@router.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """通用对话流式接口（可选 RAG 增强）。

    请求体：
        {
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！有什么可以帮你？"},
                {"role": "user", "content": "介绍一下自己"}
            ],
            "kb_id": null  // 可选，提供时启用 RAG
        }

    响应（SSE）：
        data: {"type": "contexts", "contexts": ["..."]}  (仅 RAG 模式)
        data: {"type": "token", "token": "..."}
        data: {"type": "done"}
    """
    # 参数校验
    if not request.messages:
        raise HTTPException(status_code=400, detail="消息不能为空")

    last_msg = request.messages[-1]
    if not last_msg.get("content", "").strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # SSE 流式生成器：逐块调用 rag_chat_stream 并以 data: 格式输出
    async def event_generator():
        try:
            async for chunk in rag_chat_stream(
                request.messages, request.kb_id,
                stream=request.stream,
                show_reasoning=request.show_reasoning,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'对话失败: {exc}'}, ensure_ascii=False)}\n\n"

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
        raise HTTPException(status_code=400, detail="问题不能为空")

    if not request.kb_id:
        raise HTTPException(status_code=400, detail="请先选择一个知识库")

    try:
        result = ask(request.question, request.kb_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"问答失败: {exc}") from exc

    return AskResponse(
        question=result["input"],
        answer=result["answer"],
        contexts=[doc.page_content for doc in result["context"]],
    )


@router.post("/ask/stream")
def ask_stream_endpoint(request: AskRequest) -> StreamingResponse:
    """流式 RAG 问答接口（先返回上下文，再逐 token 输出回答）。"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    if not request.kb_id:
        raise HTTPException(status_code=400, detail="请先选择一个知识库")

    async def event_generator():
        try:
            async for chunk in ask_stream(request.question, request.kb_id):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'问答失败: {exc}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
