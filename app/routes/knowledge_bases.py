"""知识库管理路由。"""

import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.models import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseDocumentsResponse,
    KnowledgeBaseDocumentInfo,
    KnowledgeBaseResponse,
)

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
    append_documents_to_knowledge_base,
    build_vector_store_from_directory,
    build_vector_store_from_documents,
)
from rag.vectorstore_chroma import load_vector_store

router = APIRouter()


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseResponse])
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


@router.get("/knowledge-base-types")
def list_kb_types() -> dict:
    """列出支持的知识库类型。"""
    return {"types": [{"value": k, "label": v} for k, v in KB_TYPES.items()]}


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse)
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


@router.delete("/knowledge-bases/{kb_id}")
def delete_kb_endpoint(kb_id: str) -> dict:
    """删除知识库。"""
    try:
        deleted = delete_knowledge_base(kb_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")

    return {"status": "ok", "message": "知识库已删除"}


@router.get("/knowledge-bases/{kb_id}/documents", response_model=KnowledgeBaseDocumentsResponse)
def list_kb_documents_endpoint(kb_id: str) -> KnowledgeBaseDocumentsResponse:
    """列出指定知识库内的文档信息（按 source 分组统计）。"""
    kb = get_knowledge_base(kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    try:
        vector_store = load_vector_store(kb.collection_name)
        data = vector_store._collection.get(include=["metadatas"])
        metadatas = data.get("metadatas") or []

        grouped: dict[str, dict[str, object]] = defaultdict(lambda: {"chunks": 0, "chapters": set()})
        for meta in metadatas:
            source = meta.get("source") or "未知来源"
            grouped[source]["chunks"] = int(grouped[source]["chunks"]) + 1  # type: ignore[assignment]
            chapter = meta.get("chapter")
            if chapter:
                grouped[source]["chapters"].add(chapter)  # type: ignore[union-attr]

        documents = [
            KnowledgeBaseDocumentInfo(
                file_name=Path(source).name,
                chunks=info["chunks"],  # type: ignore[arg-type]
                chapters=sorted(info["chapters"]),  # type: ignore[arg-type]
            )
            for source, info in sorted(grouped.items())
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取文档信息失败: {exc}") from exc

    return KnowledgeBaseDocumentsResponse(
        kb_id=kb.id,
        kb_name=kb.name,
        total_chunks=sum(doc.chunks for doc in documents),
        documents=documents,
    )


@router.post("/knowledge-bases/{kb_id}/build")
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


@router.post("/knowledge-bases/{kb_id}/upload")
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
