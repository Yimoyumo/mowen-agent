"""FastAPI 应用实例与中间件配置。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="墨问 - AI 助手",
    description="通用 AI 助手 API，支持多轮对话与可选 RAG 知识库增强",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 导入路由注册
from app.routes import chat, config, knowledge_bases  # noqa: E402

app.include_router(chat.router, tags=["对话"])
app.include_router(config.router, tags=["配置"])
app.include_router(knowledge_bases.router, tags=["知识库"])
