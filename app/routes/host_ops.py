"""执行状态路由：宿主操作审计查询 / 取消 / 工作区文件树。

- GET  /api/host/ops → ops_audit.list_ops + executor.status()
- POST /api/host/ops/{op_id}/cancel → executor.cancel（host 模式支持）
- GET  /api/host/workspace → 列出会话工作区文件树（限制在工作区内）
"""

from pathlib import Path

from fastapi import APIRouter

from app.errors import ForbiddenError, NotFoundError, ValidationError
from server.agent import ops_audit
from server.agent.executor import get_executor
from server.agent.executor.base import is_under, resolve_in_workspace
from server.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

_WORKSPACE_ENTRY_LIMIT = 500


@router.get("/host/ops")
def list_host_ops(session_id: str | None = None, limit: int = 50) -> dict:
    """列出宿主操作审计记录与执行器状态。

    响应形状与前端契约一致（顶层扁平化）：
    {"mode": str, "running": [...], "ops": [...], "executor": {完整执行器状态}}
    """
    ops = ops_audit.list_ops(session_id, limit)
    try:
        ex_status = get_executor().status()
    except Exception as exc:
        logger.warning("读取执行器状态失败: %s", exc)
        ex_status = {}
    return {
        "mode": ex_status.get("mode", "host"),
        "running": ex_status.get("running", []),
        "ops": ops,
        # 保留完整执行器状态（含 workspace_root），前端暂不使用但便于调试
        "executor": ex_status,
    }


@router.post("/host/ops/{op_id}/cancel")
async def cancel_host_op(op_id: str) -> dict:
    """取消一个运行中的宿主操作（进程组 SIGTERM→SIGKILL）。

    仅 host 模式支持；沙盒模式返回不支持。
    """
    executor = get_executor()
    if executor.status().get("mode") != "host":
        raise ValidationError("沙盒模式不支持取消操作，请在宿主机模式使用")

    if not hasattr(executor, "cancel"):
        raise ValidationError("当前执行器不支持取消操作")

    ok = await executor.cancel(op_id)
    if not ok:
        raise NotFoundError("运行中的操作")
    logger.info("已取消宿主操作: %s", op_id)
    return {"ok": True, "op_id": op_id}


@router.get("/host/workspace")
def host_workspace(session_id: str, path: str = "") -> dict:
    """列出会话工作区文件树（限制在工作区根内）。"""
    executor = get_executor()
    # workspace_root 可能返回相对路径（跟随服务器 cwd），而 walk() 产出绝对路径，
    # 必须 resolve 统一，否则 relative_to 抛 ValueError（工作区含子目录时 500）
    ws = executor.workspace_root(session_id).resolve()
    try:
        target = resolve_in_workspace(ws, path or ".").resolve()
    except Exception as exc:
        raise ForbiddenError(f"路径越界: {exc}")

    if not is_under(target, ws):
        raise ForbiddenError("路径越界（超出工作区根）")

    if not target.exists():
        return {"path": str(target), "entries": [], "entry_count": 0}

    entries = []
    walked = 0
    for root, dirs, files in target.walk():
        if walked >= _WORKSPACE_ENTRY_LIMIT:
            break
        for d in sorted(dirs):
            if walked >= _WORKSPACE_ENTRY_LIMIT:
                break
            rel = Path(root).joinpath(d).relative_to(ws)
            entries.append({"name": d, "path": str(rel), "type": "dir", "size": 0})
            walked += 1
        for f in sorted(files):
            if walked >= _WORKSPACE_ENTRY_LIMIT:
                break
            fp = Path(root).joinpath(f)
            rel = fp.relative_to(ws)
            try:
                size = fp.stat().st_size
            except OSError:
                size = 0
            entries.append({"name": f, "path": str(rel), "type": "file", "size": size})
            walked += 1

    return {
        "path": str(target),
        "entries": entries,
        "entry_count": len(entries),
    }
