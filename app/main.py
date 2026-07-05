"""FastAPI 应用实例与中间件配置。

本模块创建 FastAPI 应用实例，配置 CORS 跨域中间件，
并注册所有路由模块。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="墨问 - AI 助手",
    description="通用 AI 助手 API，支持多轮对话与可选 RAG 知识库增强",
    version="0.3.0",
)

# CORS 跨域配置：允许前端（不同端口/域名）访问本 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],       # 允许所有 HTTP 方法
    allow_headers=["*"],       # 允许所有请求头
)

# 导入并注册路由模块
from app.routes import chat, config, knowledge_bases  # noqa: E402

app.include_router(chat.router, tags=["对话"])
app.include_router(config.router, tags=["配置"])
app.include_router(knowledge_bases.router, tags=["知识库"])
