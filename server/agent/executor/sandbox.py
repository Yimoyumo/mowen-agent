"""沙盒执行器适配器：把现有 Docker 沙盒（server/agent/sandbox.py）包装成统一执行器接口。

仅做包装转发，绝不修改原 sandbox.py 的逻辑：
- 所有同步调用通过 asyncio.to_thread 包裹（避免阻塞事件循环）
- workspace_root 返回沙盒工作区的宿主路径，供路径信任根判断使用
- import_file 直接透传 Sandbox.import_file
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from server.core.logging_config import get_logger
from server.agent.executor.base import (
    ExecResult,
    WorkspaceExecutor,
    new_op_id,
)

logger = get_logger(__name__)

# 沙盒工作区宿主路径（与 server/agent/sandbox.py 中的 _SANDBOX_WORKSPACE_DIR 对应）
_SANDBOX_WORKSPACE_DIR = Path("data/sandbox_workspaces")


class SandboxExecutor(WorkspaceExecutor):
    """包装现有 Docker 沙盒的适配器。"""

    def __init__(self, config: dict | None = None):
        # 惰性导入：仅在使用沙盒模式时才加载 docker 依赖
        from server.agent import sandbox as _sb

        self._sb = _sb
        self._cfg = config or {}

    # ==================== 工作区 ====================

    def workspace_root(self, session_id: str) -> Path:
        """返回沙盒工作区的宿主路径（用于路径信任根判断）。

        注意：真正的文件系统在容器内，这里只提供宿主机侧的挂载点路径。
        """
        ws = _SANDBOX_WORKSPACE_DIR.resolve() / (session_id or "default")
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def _sandbox(self, session_id: str):
        """获取/创建会话沙盒（惰性导入池函数）。"""
        return self._sb.get_or_create(session_id)

    # ==================== 命令执行 ====================

    async def run(
        self, session_id: str, command: str, timeout: int = 30, op_id: str | None = None
    ) -> ExecResult:
        """在沙盒中执行命令。"""
        sb = self._sandbox(session_id)
        exit_code, output = await asyncio.to_thread(sb.exec, command, timeout)
        timed_out = exit_code == -1 and "命令执行超时" in output
        return ExecResult(
            exit_code=exit_code,
            output=output,
            timed_out=timed_out,
            op_id=op_id or new_op_id(),
        )

    # ==================== 文件操作 ====================

    async def write_file(self, session_id: str, path: str, content: str) -> None:
        """在沙盒中创建 / 覆盖文本文件。"""
        sb = self._sandbox(session_id)
        await asyncio.to_thread(sb.write_file, path, content)

    async def write_bytes(self, session_id: str, path: str, data: bytes) -> None:
        """在沙盒中写入二进制文件（经 base64 传输并在容器内解码）。"""
        import base64
        sb = self._sandbox(session_id)
        b64 = base64.b64encode(data).decode()
        # base64 输出仅含 [A-Za-z0-9+/=]，无 shell 元字符，安全
        cmd = f"echo {b64} | base64 -d > {path}"
        exit_code, output = await asyncio.to_thread(sb.exec, cmd)
        if exit_code != 0:
            logger.warning("沙盒写二进制失败: path=%s output=%s", path, output[:200])

    async def read_file(self, session_id: str, path: str) -> str:
        """读取沙盒中的文件内容。"""
        sb = self._sandbox(session_id)
        return await asyncio.to_thread(sb.read_file, path)

    async def list_dir(self, session_id: str, path: str = "") -> str:
        """列出沙盒目录内容。"""
        sb = self._sandbox(session_id)
        target = path if path else "/workspace"
        return await asyncio.to_thread(sb.list_dir, target)

    # ==================== 导入 / 导出 ====================

    async def export_file(self, session_id: str, path: str) -> tuple[str, str] | None:
        """从沙盒导出文件到宿主机 downloads 目录。"""
        sb = self._sandbox(session_id)
        return await asyncio.to_thread(sb.export_file, path)

    async def import_file(
        self, session_id: str, host_path: str, subpath: str | None = None
    ) -> str | None:
        """将宿主机文件导入沙盒。"""
        sb = self._sandbox(session_id)
        return await asyncio.to_thread(sb.import_file, host_path, subpath)

    # ==================== 生命周期 & 状态 ====================

    def destroy_session(self, session_id: str) -> None:
        """销毁指定会话的沙盒。"""
        self._sb.destroy(session_id)

    def destroy_all(self) -> None:
        """销毁全部沙盒（应用关闭时调用）。"""
        self._sb.destroy_all()

    def status(self) -> dict:
        """返回沙盒执行器状态。"""
        pool = self._sb.pool_status()
        return {
            "mode": "sandbox",
            "running": [],
            "pool_total": pool.get("total", 0),
            "pool_max": pool.get("max", 0),
            "workspace_root": str(_SANDBOX_WORKSPACE_DIR.resolve()),
        }
