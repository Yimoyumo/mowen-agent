"""FastAPI 应用实例与中间件配置。

本模块创建 FastAPI 应用实例，并注册所有路由模块。
开发环境通过 Vite proxy 代理 /api 到本服务，无需 CORS。
生产环境通过 nginx 等反向代理处理跨域。
"""

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.logging_config import get_logger, setup_logging, set_request_id, get_request_id
from server.db import db
from app.errors import AppException

# 初始化日志系统（幂等，首次调用生效）
setup_logging()
logger = get_logger("app")

# 初始化数据库（建表 + JSON 迁移，幂等）
db.init()


app = FastAPI(
    title="墨问 - AI 助手",
    description="通用 AI 助手 API，支持多轮对话与可选 RAG 知识库增强",
    version="0.3.0",
)


# ==================== 中间件 ====================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件：记录每个 HTTP 请求的方法、路径、耗时、状态码。

    为每个请求生成唯一 request_id，注入日志上下文，
    方便在日志中追踪一次请求的完整链路。
    """
    # 跳过健康检查等高频无意义请求
    path = request.url.path
    if path in ("/api/health", "/favicon.ico"):
        return await call_next(request)

    # 生成请求 ID 并注入日志上下文
    request_id = uuid.uuid4().hex[:8]
    set_request_id(request_id)

    method = request.method
    logger.info("--> %s %s", method, path)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error("<-- %s %s | 500 | %.0fms | 内部异常", method, path, elapsed_ms, exc_info=True)
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    # SSE 流式响应（200）或普通响应
    if response.status_code >= 400:
        logger.warning("<-- %s %s | %d | %.0fms", method, path, response.status_code, elapsed_ms)
    else:
        logger.info("<-- %s %s | %d | %.0fms", method, path, response.status_code, elapsed_ms)

    # 将 request_id 写入响应头，方便前端/排错时关联
    response.headers["X-Request-ID"] = request_id
    return response


# ==================== 全局异常处理 ====================

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """处理业务异常，返回统一格式。

    AppException 携带 code + message，detail 仅写日志不返回用户。
    """
    request_id = get_request_id()
    logger.warning(
        "业务异常 | request_id=%s path=%s | code=%s message=%s detail=%s",
        request_id, request.url.path, exc.code, exc.message, exc.internal_detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """捕获未处理的异常，返回统一格式，避免泄露内部堆栈。

    完整堆栈写入日志，用户只看到通用错误消息 + request_id。
    """
    request_id = get_request_id()
    logger.error(
        "未处理异常 | request_id=%s path=%s | %s",
        request_id, request.url.path, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "request_id": request_id,
        },
    )


# 导入并注册路由模块
from app.routes import chat, config, files, knowledge_bases, memory, settings  # noqa: E402
from app.cleanup import start_cleanup_task  # noqa: E402

app.include_router(chat.router, tags=["对话"])
app.include_router(config.router, tags=["配置"])
app.include_router(files.router, tags=["文件"])
app.include_router(knowledge_bases.router, tags=["知识库"])
app.include_router(memory.router, tags=["记忆"])
app.include_router(settings.router, tags=["用户设置"])


# ==================== 启动/关闭事件 ====================

@app.on_event("startup")
async def _on_startup():
    """应用启动时执行：启动文件清理后台任务。"""
    start_cleanup_task()


@app.on_event("shutdown")
async def _on_shutdown():
    """应用关闭时执行：停止后台任务。"""
    from app.cleanup import stop_cleanup_task
    stop_cleanup_task()
