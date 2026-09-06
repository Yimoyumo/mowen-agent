"""宿主机执行器：直接在宿主机上执行命令与文件操作（去沙盒化默认模式）。

与旧 Docker 沙盒不同，HostExecutor 直接在宿主机进程中执行：
- 命令通过独立的 shell 进程组运行，便于组杀
- 仅传白名单环境变量，绝不透传服务进程完整 env（防止 API Key 等敏感信息泄露）
- 输出累计读取，超出上限自动截断并杀进程
- 超时自动 SIGTERM → SIGKILL 结束进程组
- 文件操作仅允许在工作区根目录内（is_under 信任根校验）
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import time
import uuid
from pathlib import Path

from server.core.logging_config import get_logger
from server.agent.executor.base import (
    ExecResult,
    WorkspaceExecutor,
    is_under,
    new_op_id,
    resolve_in_workspace,
)

logger = get_logger(__name__)

_DEFAULT_WORKSPACE_ROOT = "data/host_workspaces"  # 默认工作区根目录
_DOWNLOADS_DIR = Path("downloads")                # 文件导出目录（与 /api/download 路由兼容）

_MAX_OUTPUT_BYTES = 256 * 1024      # 命令输出累计上限（256KB），超出后截断并杀进程
_READ_CAP = 200 * 1024              # read_file 单文件读取上限（200KB）
_READ_CHUNK = 8192                  # 输出读取块大小
_SIGKILL_WAIT = 3                   # SIGTERM 后等待秒数，超时则 SIGKILL

# env 白名单：仅透传这些变量，绝不透传服务进程完整 env
_ENV_KEYS = {
    "LANG": "C.UTF-8",
    "TZ": "Asia/Shanghai",
    "PYTHONUNBUFFERED": "1",
}


def _build_env(workspace: Path) -> dict[str, str]:
    """构造命令执行的 env 白名单。

    Args:
        workspace: 本次执行的会话工作区，作为 HOME
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        **_ENV_KEYS,
        "HOME": str(workspace),
    }
    return env


class HostExecutor(WorkspaceExecutor):
    """宿主机实现的工作区执行器。"""

    def __init__(self, config: dict | None = None):
        self._cfg = config or {}
        ws_root = str(self._cfg.get("workspace_root") or _DEFAULT_WORKSPACE_ROOT)
        self._workspace_root = Path(ws_root)
        self._max_output = int(self._cfg.get("max_output_bytes") or _MAX_OUTPUT_BYTES)
        self._read_cap = int(self._cfg.get("read_cap_bytes") or _READ_CAP)
        # op_id → {"session_id","command","process","started_at"}
        self._running: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        # 已被外部 cancel() 显式取消的 op_id 集合（用于 run() 收尾时置 cancelled=True）
        self._cancelled: set[str] = set()

    # ==================== 工作区 ====================

    def workspace_root(self, session_id: str) -> Path:
        """返回（并确保存在）指定会话的工作区目录。

        Args:
            session_id: 会话 id；为空时使用 "default"
        """
        ws = self._workspace_root / (session_id or "default")
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def _safe_ws_path(self, ws: Path, path: str) -> Path:
        """将路径解析到工作区内，并做信任根校验。

        解析到工作区根之外（绝对路径 / ../ 逃逸）时抛出 ValueError。

        Raises:
            ValueError: 路径越界，超出工作区根。
        """
        target = resolve_in_workspace(ws, path if path else ".")
        if not is_under(target, ws):
            raise ValueError(f"路径越界（超出工作区根）: {path}")
        return target

    # ==================== 命令执行 ====================

    async def run(
        self, session_id: str, command: str, timeout: int = 30, op_id: str | None = None
    ) -> ExecResult:
        """在宿主机工作区中执行 shell 命令。

        Args:
            session_id: 会话 id
            command: shell 命令
            timeout: 超时秒数；0 或负值视为立即超时保护（至少 1 秒）
            op_id: 可选预生成操作 id（供审计与取消保持一致）
        """
        ws = self.workspace_root(session_id)
        if timeout is None or timeout <= 0:
            timeout = 1
        op_id = op_id or new_op_id()

        proc = await asyncio.create_subprocess_shell(
            str(command),
            cwd=str(ws),
            env=_build_env(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # 独立进程组，便于组杀
        )

        entry = {
            "session_id": session_id,
            "command": str(command),
            "process": proc,
            "started_at": time.time(),
        }
        async with self._lock:
            self._running[op_id] = entry

        try:
            drain_task = asyncio.ensure_future(self._drain(proc))

            timed_out = False
            try:
                # shield 保证超时取消外层任务时，drain_task 不被取消（仍可继续收尸）
                await asyncio.wait_for(asyncio.shield(drain_task), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await self._terminate_pg(proc)
                await drain_task  # 等 kill 后管道 EOF，收完剩余输出

            output, killed = drain_task.result()

            # 收尸：确保进程真正退出并取得退出码
            return_code = await self._reap(proc)

            # 是否被外部 cancel() 显式取消（区别于超时）
            async with self._lock:
                cancelled = op_id in self._cancelled
                if cancelled:
                    self._cancelled.discard(op_id)

            if cancelled:
                output += "\n（操作已被取消）" if output.strip() else "（操作已被取消）"
                return ExecResult(
                    exit_code=-1, output=output, timed_out=False,
                    cancelled=True, op_id=op_id,
                )

            if timed_out:
                output += f"\n（命令执行超时：超过 {timeout} 秒限制，已自动终止）"
                return ExecResult(exit_code=-1, output=output, timed_out=True, op_id=op_id)

            # 被杀（截断）/ 未拿到退出码 → 统一为 -1
            if killed or return_code < 0:
                return_code = -1
            return ExecResult(
                exit_code=return_code, output=output, timed_out=False, cancelled=False, op_id=op_id
            )

        finally:
            async with self._lock:
                self._running.pop(op_id, None)

    async def _drain(self, proc) -> tuple[str, bool]:
        """读取子进程输出，累计到上限后截断并杀进程组。

        Returns:
            (输出文本, 是否因输出过长而杀进程)
        """
        buf = bytearray()
        killed = False
        while True:
            chunk = await proc.stdout.read(_READ_CHUNK)
            if not chunk:
                break
            remaining = self._max_output - len(buf)
            if remaining <= 0:
                killed = True
                self._kill_pg(proc)
                continue  # 继续排空，避免管道阻塞；进程被 kill 后管道会 EOF
            if len(chunk) > remaining:
                buf.extend(chunk[:remaining])
                killed = True
                self._kill_pg(proc)
            else:
                buf.extend(chunk)

        output = buf.decode("utf-8", errors="replace")
        if killed:
            output += "\n（输出过长已截断）"
        return output, killed

    async def _reap(self, proc) -> int:
        """等待进程退出并返回退出码（含 kill 兜底）。"""
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            # 极端情况：进程仍在运行，直接杀组
            self._kill_pg(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        return proc.returncode if proc.returncode is not None else -1

    def _kill_pg(self, proc) -> None:
        """对进程组发送 SIGTERM（尽力而为，忽略已退出错误）。"""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return  # 进程已退出
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    async def _terminate_pg(self, proc) -> None:
        """SIGTERM 整个进程组，等待一段时间仍未退出则 SIGKILL。"""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=_SIGKILL_WAIT)
            return
        except asyncio.TimeoutError:
            pass
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            await proc.wait()
        except Exception:
            pass

    async def cancel(self, op_id: str) -> bool:
        """取消运行中的操作（SIGTERM → SIGKILL）。

        Args:
            op_id: 运行中操作 id（来自 run() 返回的 ExecResult.op_id）

        Returns:
            是否存在该操作；不存在返回 False。
        """
        async with self._lock:
            entry = self._running.get(op_id)
        if not entry:
            return False
        proc = entry["process"]
        # 进程已自然结束的不再标记 cancelled（避免成功命令被误判为已取消）
        if proc.returncode is not None:
            return True
        async with self._lock:
            self._cancelled.add(op_id)
        await self._terminate_pg(proc)
        return True

    # ==================== 文件操作 ====================

    async def write_file(self, session_id: str, path: str, content: str) -> None:
        """在工作区中创建 / 覆盖文件。"""
        ws = self.workspace_root(session_id)
        target = self._safe_ws_path(ws, path)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _write():
            target.write_text(content, encoding="utf-8")

        await asyncio.to_thread(_write)

    async def write_bytes(self, session_id: str, path: str, data: bytes) -> None:
        """在工作区中写入二进制文件（如图片）。"""
        ws = self.workspace_root(session_id)
        target = self._safe_ws_path(ws, path)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _write_bytes():
            target.write_bytes(data)

        await asyncio.to_thread(_write_bytes)

    async def read_file(self, session_id: str, path: str) -> str:
        """读取工作区中的文件内容（上限 200KB，超限截断）。"""
        ws = self.workspace_root(session_id)
        try:
            target = self._safe_ws_path(ws, path)
        except ValueError:
            return f"（文件不存在或无法读取: {path}）"
        if not target.is_file():
            return f"（文件不存在或无法读取: {path}）"

        def _read():
            return target.read_bytes()

        try:
            data = await asyncio.to_thread(_read)
        except OSError as exc:
            logger.warning("读取文件失败: %s err=%s", path, exc)
            return f"（文件不存在或无法读取: {path}）"
        if len(data) > self._read_cap:
            data = data[: self._read_cap]
            text = data.decode("utf-8", errors="replace")
            return text + "\n（文件过大，已截断）"
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return f"（文件不存在或无法读取: {path}）"

    async def list_dir(self, session_id: str, path: str = "") -> str:
        """列出工作区目录内容（ls -lah）。"""
        ws = self.workspace_root(session_id)
        try:
            target = self._safe_ws_path(ws, path if path else ".")
        except ValueError:
            return f"（目录不存在或无法列出: {path or '/'}）"
        result = await self.run(session_id, f"ls -lah {_shell_quote(str(target))}", timeout=15)
        if result.exit_code != 0 and not result.timed_out:
            return f"（目录不存在或无法列出: {path or '/'}）\n{result.output}"
        return result.output

    # ==================== 导入 / 导出 ====================

    async def export_file(self, session_id: str, path: str) -> tuple[str, str] | None:
        """将工作区文件导出到 downloads 目录，返回 (token, filename)。

        与现有 /api/download/{token}/{filename} 路由兼容。
        """
        ws = self.workspace_root(session_id)
        try:
            target = self._safe_ws_path(ws, path)
        except ValueError:
            logger.warning("导出文件路径越界: %s", path)
            return None
        if not target.is_file():
            logger.warning("导出文件不存在: %s", path)
            return None

        filename = target.name
        token = str(uuid.uuid4())[:8]
        dest_dir = _DOWNLOADS_DIR / token
        dest_path = dest_dir / filename

        def _copy():
            _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(target), str(dest_path))

        try:
            await asyncio.to_thread(_copy)
        except OSError as exc:
            logger.error("导出文件失败: %s err=%s", path, exc)
            return None
        logger.info("文件已导出: %s -> %s", target, dest_path)
        return token, filename

    async def import_file(
        self, session_id: str, host_path: str, subpath: str | None = None
    ) -> str | None:
        """从宿主机路径复制文件到工作区，返回工作区目标路径。"""
        src = Path(host_path)
        if not src.is_file():
            return None
        ws = self.workspace_root(session_id)
        filename = subpath or src.name
        target = self._safe_ws_path(ws, filename)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _copy():
            shutil.copy2(str(src), str(target))

        try:
            await asyncio.to_thread(_copy)
        except OSError as exc:
            logger.error("导入文件失败: %s err=%s", src, exc)
            return None
        logger.info("文件已导入: %s -> %s", src, target)
        return str(target)

    # ==================== 生命周期 & 状态 ====================

    def destroy_session(self, session_id: str) -> None:
        """销毁指定会话的工作区（删除目录）。"""
        ws = self.workspace_root(session_id)
        self._rmtree(ws)

    def destroy_all(self) -> None:
        """应用关闭时的清理。

        注意：宿主机工作区是**持久数据**（同一会话跨消息、跨重启保留），
        关闭时**不删除**盘上文件——磁盘占用由 app/cleanup.py 的
        workspace_retention_days 保留策略（默认 7 天）负责。

        历史教训：早期实现会在关闭时 rmtree 整个工作区根目录；而开发模式
        uvicorn --reload 会监视 cwd 下所有 .py（含 Agent 写入 data/ 的工作区
        脚本），Agent 每写一个 .py 就触发一次重启 → 每次重启清空全部工作区，
        造成"文件跨用户消息丢失"。此处已改为仅清理内存态。
        """
        self._running.clear()

    def _rmtree(self, path: Path) -> None:
        """删除目录（尽力而为，不存在时静默跳过）。"""
        if path.exists() and path.is_dir():
            shutil.rmtree(str(path), ignore_errors=True)
            logger.info("工作区已销毁: %s", path)

    def status(self) -> dict:
        """返回执行器状态。"""
        now = time.time()
        running = [
            {
                "op_id": op_id,
                "session_id": e["session_id"],
                "command": e["command"],
                "started_at": e["started_at"],
                "elapsed": round(now - e["started_at"], 2),
            }
            for op_id, e in self._running.items()
        ]
        return {
            "mode": "host",
            "running": running,
            "workspace_root": str(self._workspace_root.resolve()),
        }


def _shell_quote(command: str) -> str:
    """shell 单引号引用，避免注入。"""
    return "'" + command.replace("'", "'\\''") + "'"
