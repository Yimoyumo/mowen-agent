"""Pydantic 数据模型定义。"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """通用对话请求。"""
    messages: list[dict]
    kb_id: str | None = None


class AskRequest(BaseModel):
    """旧版 RAG 问答请求（保留兼容）。"""
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


class KnowledgeBaseDocumentInfo(BaseModel):
    file_name: str
    chunks: int
    chapters: list[str]


class KnowledgeBaseDocumentsResponse(BaseModel):
    kb_id: str
    kb_name: str
    total_chunks: int
    documents: list[KnowledgeBaseDocumentInfo]


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
