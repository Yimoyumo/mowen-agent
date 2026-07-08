"""异常体系测试。

测试内容：
- AppException 基类属性
- 各子类 status_code 和 code
- 异常消息和 detail
- 异常可被 FastAPI HTTPException 捕获
"""

import pytest
from fastapi import HTTPException

from app.errors import (
    AppException,
    ValidationError,
    NotFoundError,
    ForbiddenError,
    ConflictError,
    RateLimitError,
    InternalError,
    ServiceUnavailableError,
)


class TestAppException:
    """AppException 基类测试。"""

    def test_default_values(self):
        exc = AppException()
        assert exc.code == "INTERNAL_ERROR"
        assert exc.status_code == 500
        assert exc.message == "服务器内部错误"

    def test_custom_message(self):
        exc = AppException("自定义错误")
        assert exc.message == "自定义错误"
        assert exc.detail == "自定义错误"  # HTTPException.detail 返回 message

    def test_custom_detail(self):
        exc = AppException("用户消息", detail="内部调试信息")
        assert exc.message == "用户消息"
        assert exc.internal_detail == "内部调试信息"

    def test_custom_status_code(self):
        exc = AppException("error", status_code=418)
        assert exc.status_code == 418

    def test_is_http_exception(self):
        exc = AppException("test")
        assert isinstance(exc, HTTPException)


class TestValidationError:
    """ValidationError (400) 测试。"""

    def test_defaults(self):
        exc = ValidationError()
        assert exc.status_code == 400
        assert exc.code == "VALIDATION_ERROR"

    def test_message(self):
        exc = ValidationError("名称不能为空")
        assert exc.message == "名称不能为空"
        assert exc.detail == "名称不能为空"

    def test_with_detail(self):
        exc = ValidationError("校验失败", detail="字段 x 为空")
        assert exc.internal_detail == "字段 x 为空"


class TestNotFoundError:
    """NotFoundError (404) 测试。"""

    def test_defaults(self):
        exc = NotFoundError()
        assert exc.status_code == 404
        assert exc.code == "NOT_FOUND"

    def test_message(self):
        exc = NotFoundError("知识库不存在")
        assert exc.message == "知识库不存在"


class TestForbiddenError:
    """ForbiddenError (403) 测试。"""

    def test_defaults(self):
        exc = ForbiddenError()
        assert exc.status_code == 403
        assert exc.code == "FORBIDDEN"


class TestConflictError:
    """ConflictError (409) 测试。"""

    def test_defaults(self):
        exc = ConflictError()
        assert exc.status_code == 409
        assert exc.code == "CONFLICT"


class TestRateLimitError:
    """RateLimitError (429) 测试。"""

    def test_defaults(self):
        exc = RateLimitError()
        assert exc.status_code == 429
        assert exc.code == "RATE_LIMITED"


class TestInternalError:
    """InternalError (500) 测试。"""

    def test_defaults(self):
        exc = InternalError()
        assert exc.status_code == 500
        assert exc.code == "INTERNAL_ERROR"

    def test_with_detail(self):
        exc = InternalError("操作失败", detail="DB connection lost")
        assert exc.message == "操作失败"
        assert exc.internal_detail == "DB connection lost"
        # detail 不暴露给用户
        assert exc.detail == "操作失败"  # HTTPException.detail 是用户可见的


class TestServiceUnavailableError:
    """ServiceUnavailableError (503) 测试。"""

    def test_defaults(self):
        exc = ServiceUnavailableError()
        assert exc.status_code == 503
        assert exc.code == "SERVICE_UNAVAILABLE"


class TestExceptionRaising:
    """异常抛出和捕获测试。"""

    def test_raise_and_catch(self):
        with pytest.raises(NotFoundError) as exc_info:
            raise NotFoundError("资源不存在")
        assert exc_info.value.status_code == 404
        assert "资源不存在" in exc_info.value.detail

    def test_raise_with_from(self):
        with pytest.raises(InternalError) as exc_info:
            try:
                raise ValueError("原始错误")
            except ValueError as e:
                raise InternalError("操作失败", detail=str(e)) from e
        assert exc_info.value.internal_detail == "原始错误"

    def test_catch_as_base_class(self):
        """所有子类都可以被 AppException 捕获。"""
        for exc_cls in [ValidationError, NotFoundError, ForbiddenError, ConflictError,
                        RateLimitError, InternalError, ServiceUnavailableError]:
            with pytest.raises(AppException):
                raise exc_cls("test")
