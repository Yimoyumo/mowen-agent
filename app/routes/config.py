"""配置与健康检查路由。"""

from fastapi import APIRouter

from app.models import ConfigResponse, ModelContextInfo
from server.user_settings import user_settings, build_config

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """健康检查接口，供前端确认后端是否在线。"""
    return {"status": "ok"}


@router.get("/config", response_model=ConfigResponse)
def config_endpoint() -> ConfigResponse:
    """获取当前系统配置（只读，从 user_settings 加载）。"""
    cfg = build_config(user_settings.load())
    info = cfg.get_active_model_info()
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
        context_window=info["context_window"],
        max_output=info["max_output"],
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        thinking=cfg.enable_thinking,
        reasoning_effort=cfg.reasoning_effort,
    )
