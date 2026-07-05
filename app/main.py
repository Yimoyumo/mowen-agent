"""FastAPI 应用实例与中间件配置。

本模块创建 FastAPI 应用实例，并注册所有路由模块。
开发环境通过 Vite proxy 代理 /api 到本服务，无需 CORS。
生产环境通过 nginx 等反向代理处理跨域。
"""

from fastapi import FastAPI

app = FastAPI(
    title="墨问 - AI 助手",
    description="通用 AI 助手 API，支持多轮对话与可选 RAG 知识库增强",
    version="0.3.0",
)

# 导入并注册路由模块
from app.routes import chat, config, files, knowledge_bases  # noqa: E402

app.include_router(chat.router, tags=["对话"])
app.include_router(config.router, tags=["配置"])
app.include_router(files.router, tags=["文件"])
app.include_router(knowledge_bases.router, tags=["知识库"])
