"""统一 HITL 交互模块：权限审批与 Agent 主动提问共用同一机制。

用途：
- 权限审批：工具执行危险命令 / 文件操作前，向用户弹出审批卡片等待确认。
- 主动提问：Agent 在缺少关键信息时通过 ask_user 工具向用户提问。

机制：
- 审批 / 提问都通过 `request()` 在当前事件循环中挂起一个 asyncio.Future，
  同时向事件队列 emit 一个 interaction_request 事件（由前端 SSE 消费并渲染卡片）。
- 用户在 REST 端点调用 `answer()` 时，用该 request 的 future 回填结果。
- 事件队列通过 ContextVar 传给 pump 任务（含工具内部），保证同一条 SSE 流。
- 审批 scope 缓存：session 级存内存，"always" 写入 user_settings 的
  executor_config["persistent_allow"]（用 update() 深合并）。
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from server.core.logging_config import get_logger

logger = get_logger(__name__)


# ==================== ContextVar：UI 开关与事件队列 ====================

_ui_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar("ui_enabled", default=True)
_event_queue: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "event_queue", default=None
)


def set_ui_enabled(v: bool) -> None:
    """开启 / 关闭人机交互（非流式/无人值守时设为 False，审批/提问将快速 fail）。"""
    _ui_enabled.set(v)


def set_event_queue(q: asyncio.Queue | None) -> None:
    """设置事件队列（由 graph 的 SSE pump 创建并注入）。"""
    _event_queue.set(q)


def emit(event: dict) -> None:
    """向事件队列发送一个事件（无队列则丢弃，不阻塞）。"""
    q = _event_queue.get()
    if q is None:
        return
    try:
        q.put_nowait(("interaction", event))
    except asyncio.QueueFull:
        logger.warning("交互事件队列已满，丢弃事件: %s", event.get("type"))


# ==================== 交互请求 ====================

@dataclass
class InteractionRequest:
    """一次待处理的人机交互请求。"""

    request_id: str
    kind: str                       # approval / ask_user
    session_id: str
    payload: dict
    future: asyncio.Future
    timeout: int
    created_at: float


_registry: dict[str, InteractionRequest] = {}
_registry_lock = threading.Lock()

# session 级审批 scope 缓存：session_id -> set(pattern)
_session_scope_cache: dict[str, set[str]] = {}


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


# ==================== 发起请求 / 应答 ====================

async def request(
    kind: str,
    payload: dict,
    session_id: str,
    timeout: int,
) -> dict:
    """发起一次 HITL 交互请求并等待应答。

    Args:
        kind: "approval"（权限审批）或 "ask_user"（主动提问）
        payload: 附加数据（审批含 command/decision/reason/timeout；提问含 question/options 等）
        session_id: 会话 id
        timeout: 等待应答的秒数

    Returns:
        dict，含 "status"：
        - "no_ui"    : UI 未启用，立即返回（无人值守/非流式）
        - "answered" : 用户已应答，附 approved/scope/answer
        - "timeout"  : 等待超时
        - "cancelled": 等待被取消（如 SSE 断开）
    """
    base = {"kind": kind, "session_id": session_id, "payload": payload, "timeout": timeout}
    if not _ui_enabled.get():
        return {"status": "no_ui", **base}

    request_id = new_request_id()
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    req = InteractionRequest(
        request_id=request_id,
        kind=kind,
        session_id=session_id,
        payload=payload,
        future=future,
        timeout=timeout,
        created_at=time.time(),
    )
    with _registry_lock:
        _registry[request_id] = req

    emit({
        "type": "interaction_request",
        "request_id": request_id,
        "kind": kind,
        "session_id": session_id,
        "timeout": timeout,
        # payload 必须嵌套传递：payload 内含同名键（如审批的 kind="run" 是操作类型），
        # 若扁平展开会覆盖本事件的 kind="approval"/"ask_user"（交互类型），
        # 导致前端把审批卡渲染成提问卡。与 interaction.pending() 的嵌套结构保持一致。
        "payload": dict(payload),
    })

    try:
        result = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        emit({"type": "interaction_result", "request_id": request_id, "status": "timeout", "kind": kind})
        return {"status": "timeout", **base}
    except asyncio.CancelledError:
        emit({"type": "interaction_result", "request_id": request_id, "status": "cancelled", "kind": kind})
        raise
    else:
        # result 形如 {"approved": bool|None, "scope": str, "answer": str|None}
        emit({
            "type": "interaction_result",
            "request_id": request_id,
            "status": "answered",
            "kind": kind,
            "approved": result.get("approved"),
            "scope": result.get("scope"),
            "answer": result.get("answer"),
        })
        return {"status": "answered", **base, **result}
    finally:
        with _registry_lock:
            _registry.pop(request_id, None)


def answer(
    request_id: str,
    *,
    approved: bool | None = None,
    scope: str = "once",
    answer: str | None = None,
) -> bool:
    """应答一个交互请求。

    Args:
        request_id: 待应答的请求 id
        approved: 审批结果（"once" 表示单次；approval 场景必填）
        scope: 审批作用域 "once" / "session" / "always"
        answer: ask_user 的文本答案

    Returns:
        True=成功应答，False=请求不存在（已过期/已处理）。
    """
    with _registry_lock:
        req = _registry.get(request_id)
    if not req:
        return False

    # 审批通过且有作用域 → 记录 scope 缓存（供下次审批命中直接放行）
    if req.kind == "approval" and approved:
        _cache_approval(req, scope)

    result = {"approved": approved, "scope": scope, "answer": answer}
    try:
        if req.future.done():
            return False
        req.future.set_result(result)
    except (asyncio.InvalidStateError, RuntimeError) as exc:
        logger.warning("应答失败: request=%s err=%s", request_id, exc)
        return False
    return True


def pending(session_id: str | None = None) -> list[dict]:
    """列出待处理的交互请求（序列化给 REST）。

    Args:
        session_id: 只返回该会话的请求；None 返回全部。
    """
    with _registry_lock:
        items = list(_registry.values())
    result = []
    for req in items:
        if session_id and req.session_id != session_id:
            continue
        result.append({
            "request_id": req.request_id,
            "kind": req.kind,
            "session_id": req.session_id,
            "payload": req.payload,
            "timeout": req.timeout,
            "created_at": req.created_at,
            "expires_at": req.created_at + req.timeout,
        })
    return result


def remove(request_id: str) -> None:
    """从注册表移除一个交互请求。"""
    with _registry_lock:
        _registry.pop(request_id, None)


# ==================== 审批 scope 缓存 ====================

def normalize_pattern(command: str) -> str:
    """将命令归一化为匹配 pattern（首 token + "*"）。

    例："pip install flask" → "pip install *"；"rm -rf x" → "rm -rf *"。
    取前两个 token（命令 + 子命令），其余用 * 通配。
    """
    parts = command.strip().split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0] + " *"
    return f"{parts[0]} {parts[1]} *"


def normalize_file_pattern(op: str, path: str, workspace) -> str:
    """将文件操作归一化为 scope pattern：`{op}:{解析后的绝对路径}`。

    例：write /workspace/a.txt → "write:/abs/workspace/a.txt"。
    Args:
        op: 具体文件操作 read / write / edit / list / export
        path: 目标路径（相对或绝对）
        workspace: 会话工作区根（用于把相对路径解析为绝对路径）
    """
    try:
        ws = Path(workspace) if workspace else Path.cwd()
        p = Path(path)
        if not p.is_absolute():
            p = ws / p
        return f"{op}:{p.resolve()}"
    except Exception:
        return f"{op}:{path}"


def check_scope_cache(session_id: str, scope_key: str) -> bool:
    """检查 scope_key 是否命中审批 scope 缓存（命中则跳过提问直接放行）。

    Args:
        session_id: 会话 id
        scope_key: 由调用方计算好的归一化 pattern
            （命令走 normalize_pattern，文件操作走 normalize_file_pattern）
    """
    if not scope_key:
        return False
    if scope_key in _session_scope_cache.get(session_id, set()):
        return True
    # always：读取 user_settings 的 persistent_allow
    return _check_persistent_allow(scope_key)


def _cache_approval(req: InteractionRequest, scope: str) -> None:
    """记录审批作用域缓存。

    优先使用请求 payload 中调用方算好的 scope_key；否则回退到命令归一化。
    """
    scope_key = req.payload.get("scope_key") or normalize_pattern(req.payload.get("command", ""))
    if not scope_key:
        return
    if scope == "session":
        _session_scope_cache.setdefault(req.session_id, set()).add(scope_key)
        logger.info("审批 scope 缓存(session): session=%s pattern=%s", req.session_id, scope_key)
    elif scope == "always":
        _add_persistent_allow(scope_key)
        logger.info("审批 scope 缓存(always): pattern=%s", scope_key)


def _check_persistent_allow(pattern: str) -> bool:
    """检查 persistent_allow 是否包含该 pattern。"""
    try:
        from server.core.user_settings import user_settings
        ex = user_settings.load().get("executor", {})
        allow = ex.get("persistent_allow", [])
        return pattern in allow
    except Exception as exc:
        logger.debug("读取 persistent_allow 失败: %s", exc)
        return False


def _add_persistent_allow(pattern: str) -> None:
    """将 pattern 写入 user_settings.executor_config["persistent_allow"]（深合并）。"""
    try:
        from server.core.user_settings import user_settings
        data = user_settings.load()
        ex = data.get("executor", {}) or {}
        allow = list(ex.get("persistent_allow", []) or [])
        if pattern not in allow:
            allow.append(pattern)
        user_settings.update({"executor": {"persistent_allow": allow}})
    except Exception as exc:
        logger.warning("写入 persistent_allow 失败: %s", exc)
