"""统一异常体系。

定义业务异常基类和具体异常类型，配合全局异常处理器
（app/main.py 中的 exception_handler）实现：

1. 统一错误响应格式
2. 异常消息不泄露内部堆栈
3. 按异常类型自动映射 HTTP 状态码
4. 带请求 ID 便于排错

用法（路由中）：
    from app.errors import NotFoundError, ValidationError

    if not kb:
        raise NotFoundError("知识库")
    if not name:
        raise ValidationError("知识库名称不能为空")

    try:
        do_something()
    except SomeInternalError as exc:
        raise InternalError("操作失败", detail=str(exc)) from exc

响应格式（自动生成）：
    {
        "code": "NOT_FOUND",
        "message": "知识库不存在",
        "request_id": "abc12345"
    }
"""

from fastapi import HTTPException


# ==================== 基类 ====================

class AppException(HTTPException):
    """所有业务异常的基类。

    Attributes:
        code: 机器可读的错误码（如 NOT_FOUND, VALIDATION_ERROR）
        status_code: HTTP 状态码
        message: 用户可读的错误消息（不包含内部细节）
        detail: 内部细节（仅写入日志，不返回给用户，开发调试用）
    """

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "服务器内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: str | None = None,
        status_code: int | None = None,
    ):
        # 先保存到内部属性（detail 是 FastAPI HTTPException 的字段，会冲突）
        self.message = message or self.message
        self.internal_detail = detail
        if status_code:
            self.status_code = status_code
        # HTTPException.detail 会返回给前端，用用户可读的 message
        super().__init__(status_code=self.status_code, detail=self.message)


# ==================== 具体异常类型 ====================

class ValidationError(AppException):
    """请求参数校验失败（400）。"""
    code = "VALIDATION_ERROR"
    status_code = 400
    message = "请求参数错误"


class NotFoundError(AppException):
    """资源不存在（404）。"""
    code = "NOT_FOUND"
    status_code = 404
    message = "资源不存在"


class ForbiddenError(AppException):
    """无权限访问（403）。"""
    code = "FORBIDDEN"
    status_code = 403
    message = "无权访问"


class ConflictError(AppException):
    """资源冲突（409），如重名创建。"""
    code = "CONFLICT"
    status_code = 409
    message = "资源已存在"


class RateLimitError(AppException):
    """请求频率超限（429）。"""
    code = "RATE_LIMITED"
    status_code = 429
    message = "请求过于频繁，请稍后再试"


class InternalError(AppException):
    """内部错误（500），detail 写日志但不返回用户。

    用法：
        try:
            risky_operation()
        except SomeException as exc:
            raise InternalError("操作失败", detail=str(exc)) from exc
    """
    code = "INTERNAL_ERROR"
    status_code = 500
    message = "服务器内部错误"


class ServiceUnavailableError(AppException):
    """依赖服务不可用（503），如 Docker、向量库。"""
    code = "SERVICE_UNAVAILABLE"
    status_code = 503
    message = "服务暂时不可用"
