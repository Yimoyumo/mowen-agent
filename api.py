"""FastAPI 接口：提供 RAG 问答 HTTP API。

用法：
    uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000

接口：
    POST /ask                 执行 RAG 问答
    POST /ask/stream          流式执行 RAG 问答
    GET  /health              健康检查
    GET  /config              获取当前配置
    GET  /knowledge-bases     列出知识库
    POST /knowledge-bases     创建知识库
    DELETE /knowledge-bases/{kb_id} 删除知识库
    POST /knowledge-bases/{kb_id}/build  重建知识库向量库
    POST /knowledge-bases/{kb_id}/upload 上传文档到知识库（追加）
"""

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rag.config import RAGConfig
from rag.knowledge_base import (
    KB_TYPES,
    create_knowledge_base,
    delete_knowledge_base,
    ensure_default_knowledge_base,
    get_knowledge_base,
    load_knowledge_bases,
)
from rag.loader import load_documents
from rag.pipeline import (
    ask,
    ask_stream,
    build_vector_store_from_directory,
    build_vector_store_from_documents,
    append_documents_to_knowledge_base,
)

app = FastAPI(
    title="RAG 问答系统",
    description="基于智谱 AI + LangChain 的 RAG 问答 API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    kb_id: str | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    contexts: list[str]


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    kb_type: str


class CreateKnowledgeBaseRequest(BaseModel):
    name: str
    description: str = ""
    kb_type: str = "general"


class ConfigResponse(BaseModel):
    chat_provider: str
    chat_model: str
    embedding_model: str
    top_k: int
    chunk_size: int
    chunk_overlap: int
    chapter_split: bool
    chapter_chunk_threshold: int
    chapter_chunk_overlap: int
    enable_query_expansion: bool


@app.get("/health")
def health() -> dict:
    """健康检查接口。"""
    return {"status": "ok"}


@app.get("/config", response_model=ConfigResponse)
def config_endpoint() -> ConfigResponse:
    """获取当前配置（只读）。"""
    cfg = RAGConfig.from_json()
    return ConfigResponse(
        chat_provider=cfg.chat_provider,
        chat_model=cfg.chat_model,
        embedding_model=cfg.embedding_model,
        top_k=cfg.top_k,
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        chapter_split=cfg.chapter_split,
        chapter_chunk_threshold=cfg.chapter_chunk_threshold,
        chapter_chunk_overlap=cfg.chapter_chunk_overlap,
        enable_query_expansion=cfg.enable_query_expansion,
    )


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest) -> AskResponse:
    """RAG 问答接口。"""
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


@app.post("/ask/stream")
def ask_stream_endpoint(request: AskRequest) -> StreamingResponse:
    """流式 RAG 问答接口。

    先返回问题、参考上下文（JSON 行，type=context），然后逐 Token 输出回答（JSON 行，type=token）。
    """
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


@app.get("/knowledge-bases", response_model=list[KnowledgeBaseResponse])
def list_knowledge_bases() -> list[KnowledgeBaseResponse]:
    """列出所有知识库。"""
    ensure_default_knowledge_base()
    kbs = load_knowledge_bases()
    return [
        KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            created_at=kb.created_at,
            kb_type=kb.kb_type,
        )
        for kb in kbs
    ]


@app.get("/knowledge-base-types")
def list_kb_types() -> dict:
    """列出支持的知识库类型。"""
    return {"types": [{"value": k, "label": v} for k, v in KB_TYPES.items()]}


@app.post("/knowledge-bases", response_model=KnowledgeBaseResponse)
def create_kb_endpoint(request: CreateKnowledgeBaseRequest) -> KnowledgeBaseResponse:
    """创建新知识库。"""
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="知识库名称不能为空")

    kb_type = (request.kb_type or "general").strip().lower()
    if kb_type not in KB_TYPES:
        kb_type = "general"

    try:
        kb = create_knowledge_base(
            request.name.strip(),
            request.description.strip(),
            kb_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建失败: {exc}") from exc

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        created_at=kb.created_at,
        kb_type=kb.kb_type,
    )


@app.delete("/knowledge-bases/{kb_id}")
def delete_kb_endpoint(kb_id: str) -> dict:
    """删除知识库。"""
    try:
        deleted = delete_knowledge_base(kb_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")

    return {"status": "ok", "message": "知识库已删除"}


@app.post("/knowledge-bases/{kb_id}/build")
def build_kb_endpoint(kb_id: str) -> dict:
    """从默认 data 目录重建指定知识库的向量库。"""
    kb = get_knowledge_base(kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    try:
        build_vector_store_from_directory("./data", kb.collection_name, kb.kb_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"构建失败: {exc}") from exc

    return {"status": "ok", "message": f"知识库 {kb.name} 重建完成"}


@app.post("/knowledge-bases/{kb_id}/upload")
def upload_kb_endpoint(
    kb_id: str,
    file: UploadFile = File(...),
    reset: bool = Form(False),
) -> dict:
    """上传文档到指定知识库。

    默认追加文档；reset=true 时清空后重建。
    """
    kb = get_knowledge_base(kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    allowed_suffixes = {".txt", ".md", ".json", ".csv"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，仅支持 {allowed_suffixes}",
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="upload_"))
    temp_path = temp_dir / file.filename

    try:
        with temp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        documents = load_documents(temp_path)
        if reset:
            build_vector_store_from_documents(documents, kb.collection_name, kb.kb_type)
            message = f"已上传 {file.filename} 并重建知识库 {kb.name}"
        else:
            append_documents_to_knowledge_base(documents, kb.collection_name, kb.kb_type)
            message = f"已追加 {file.filename} 到知识库 {kb.name}"
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        file.file.close()

    return {"status": "ok", "message": message}
