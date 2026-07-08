"""Docker 沙盒管理器。

为 Agent 提供一个可持久操控的 Linux 环境：
- 执行任意 shell 命令（含 pip install、编译等）
- 读写文件、浏览目录
- 沙盒按会话 ID 管理，跨消息持久化（同一会话内文件不丢失）
- 超过 30 分钟空闲自动清理
- export_file: 将容器内文件导出到宿主机供用户下载
"""

import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import docker
from docker.errors import DockerException, NotFound

from server.logging_config import get_logger

logger = get_logger(__name__)

_SANDBOX_IMAGE = "mowen-sandbox:latest"  # 优先用自建镜像（预装工具），不存在时回退到 python:3.12-slim
_SANDBOX_MEMORY = "512m"
_SANDBOX_CPU = 1.0
_DEFAULT_TIMEOUT = 60          # 默认命令超时（秒）

_DOWNLOADS_DIR = Path("downloads")  # 文件导出目录
_UPLOADS_DIR = Path("uploads")      # 用户上传暂存目录

# 沙盒池配置
_MAX_SANDBOXES = 10             # 全局最大沙盒数（超过时淘汰最久未用的）
_SANDBOX_IDLE_TIMEOUT = 1800    # 30 分钟空闲自动销毁
_CLEANUP_INTERVAL = 300        # 每 5 分钟检查一次超时


class Sandbox:
    """Docker 沙盒封装。

    一个对话会话对应一个 Sandbox 实例，
    所有工具调用共享同一个容器和文件系统。
    """

    def __init__(self):
        client = docker.from_env()
        self._client = client

        # 优先用预装工具的自建镜像，不存在则回退到 slim
        image = _SANDBOX_IMAGE
        try:
            client.images.get(image)
        except Exception:
            image = "python:3.12-slim"

        self._container = client.containers.run(
            image=image,
            command=["tail", "-f", "/dev/null"],  # 保持运行
            mem_limit=_SANDBOX_MEMORY,
            nano_cpus=int(_SANDBOX_CPU * 1e9),
            working_dir="/workspace",
            security_opt=["no-new-privileges"],
            detach=True,
            remove=True,
            tty=True,
        )
        # 初始化工作区
        self._container.exec_run("mkdir -p /workspace", user="root")
        self._container.exec_run("chmod 777 /workspace", user="root")

    @property
    def container_id(self) -> str:
        return self._container.id[:12]

    def exec(self, command: str, timeout: int = _DEFAULT_TIMEOUT) -> tuple[int, str]:
        """在沙盒中执行命令，返回 (exit_code, stdout+stderr)。

        Args:
            command: shell 命令
            timeout: 超时秒数，超过则自动 kill
        """
        try:
            # 检查容器是否还活着
            try:
                self._container.reload()
            except Exception:
                return -1, "（沙盒容器已关闭，请重新开始对话）"

            # 用 timeout 命令包裹，防止死循环/长等待卡住 Agent
            wrapped = f"timeout {timeout} sh -c {_quote(command)}"
            result = self._container.exec_run(
                ["sh", "-c", wrapped],
                user="root",
                demux=False,
            )
            exit_code = result.exit_code or 0
            output = result.output.decode("utf-8", errors="replace") if result.output else ""

            # exit_code 124 = timeout 命令超时 kill
            if exit_code == 124:
                return -1, f"（命令执行超时：超过 {timeout} 秒限制，已自动终止）"

            return exit_code, output

        except Exception as exc:
            return -1, f"（沙盒命令执行失败: {exc}）"

    def write_file(self, path: str, content: str) -> None:
        """在沙盒中创建/覆盖文件。"""
        safe_content = content.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")
        cmd = f"cat > {_resolve_path(path)} << 'SANDBOX_EOF'\n{safe_content}\nSANDBOX_EOF"
        self.exec(cmd)

    def read_file(self, path: str) -> str:
        """读取沙盒中的文件内容。"""
        exit_code, output = self.exec(f"cat {_resolve_path(path)}")
        if exit_code != 0:
            return f"（文件不存在或无法读取: {path}）"
        return output

    def list_dir(self, path: str = "/workspace") -> str:
        """列出目录内容（ls -lah）。"""
        exit_code, output = self.exec(f"ls -lah {_resolve_path(path)}")
        if exit_code != 0:
            return f"（目录不存在或无法列出: {path}）"
        return output

    def export_file(self, container_path: str) -> tuple[str, str] | None:
        """将容器内文件导出到宿主机 downloads 目录。"""
        resolved = _resolve_path(container_path)
        _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        filename = Path(resolved).name
        token = str(uuid.uuid4())[:8]
        dest_dir = _DOWNLOADS_DIR / token
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        try:
            cp_result = subprocess.run(
                ["docker", "cp", f"{self._container.id}:{resolved}", str(dest_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if cp_result.returncode != 0:
                return None
            return token, filename
        except Exception:
            return None

    def import_file(self, host_path: str, container_subpath: str | None = None) -> str | None:
        """将宿主机文件导入沙盒容器。"""
        src = Path(host_path)
        if not src.is_file():
            return None

        filename = container_subpath or src.name
        dest = _resolve_path(f"/workspace/{filename}")

        try:
            cp_result = subprocess.run(
                ["docker", "cp", str(src), f"{self._container.id}:{dest}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if cp_result.returncode != 0:
                return None
            return dest
        except Exception:
            return None

    def destroy(self) -> None:
        """销毁沙盒容器。"""
        try:
            self._container.remove(force=True)
        except (NotFound, Exception):
            pass


# ==================== 沙盒池：按 session_id 管理 ====================

# _sandbox_pool: session_id → {"sandbox": Sandbox, "last_active": float}
_sandbox_pool: dict[str, dict] = {}
_pool_lock = threading.Lock()

# 记录每个 session 上传过的文件，沙盒重建时自动重新导入
_session_files: dict[str, list[dict]] = {}
_session_files_lock = threading.Lock()


def track_session_files(session_id: str, files: list[dict]) -> None:
    """记录某个 session 上传的文件列表。

    Args:
        files: [{token, filename}, ...]
    """
    if not session_id or not files:
        return
    with _session_files_lock:
        _session_files[session_id] = [dict(f) for f in files]


def _reimport_files(sb: Sandbox, files: list[dict]) -> list[dict]:
    """将宿主机文件重新导入沙盒。

    源文件缺失或过期时静默跳过。

    Returns:
        成功导入的文件列表（失败的从 tracking 中移除）
    """
    ok = []
    for f in files:
        host_path = Path(f"uploads/{f['token']}/{f['filename']}")
        suffix = Path(f.get("filename", "")).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            continue
        if not host_path.is_file():
            logger.debug("沙盒文件恢复跳过: 源文件已过期 %s", f['filename'])
            continue
        if sb.import_file(str(host_path)):
            ok.append(f)
    return ok


def get_or_create(session_id: str) -> Sandbox:
    """获取或创建沙盒（按 session_id）。

    如果池中已有该会话的沙盒且容器存活，直接复用；
    否则创建新沙盒并存入池中，同时自动重新导入已上传的文件。
    """
    with _pool_lock:
        entry = _sandbox_pool.get(session_id)
        if entry:
            try:
                entry["sandbox"]._container.reload()
                entry["last_active"] = time.time()
                logger.debug("沙盒复用: session=%s", session_id)
                return entry["sandbox"]
            except Exception:
                logger.info("沙盒容器已失效，重建: session=%s", session_id)
                del _sandbox_pool[session_id]

        if len(_sandbox_pool) >= _MAX_SANDBOXES:
            oldest_id = min(_sandbox_pool, key=lambda k: _sandbox_pool[k]["last_active"])
            old = _sandbox_pool.pop(oldest_id)
            try:
                old["sandbox"].destroy()
            except Exception:
                pass
            logger.warning("沙盒池已满，淘汰: session=%s", oldest_id)

        sb = Sandbox()
        _sandbox_pool[session_id] = {
            "sandbox": sb,
            "last_active": time.time(),
        }
        logger.info("沙盒已创建: session=%s container=%s", session_id, sb.container_id)

        # 自动重新导入之前上传的文件
        with _session_files_lock:
            files = _session_files.get(session_id, [])
        if files:
            remaining = _reimport_files(sb, files)
            # 部分文件已过期，更新 tracking
            with _session_files_lock:
                if remaining:
                    _session_files[session_id] = remaining
                else:
                    _session_files.pop(session_id, None)
            logger.info("沙盒文件已恢复: session=%s 成功=%d/%d",
                       session_id, len(remaining), len(files))

        return sb


def get(session_id: str) -> Sandbox | None:
    """获取现有沙盒，不存在返回 None。"""
    with _pool_lock:
        entry = _sandbox_pool.get(session_id)
        if not entry:
            return None
        try:
            entry["sandbox"]._container.reload()
            entry["last_active"] = time.time()
            return entry["sandbox"]
        except Exception:
            del _sandbox_pool[session_id]
            return None


def destroy(session_id: str) -> None:
    """销毁指定会话的沙盒。"""
    with _pool_lock:
        entry = _sandbox_pool.pop(session_id, None)
    if entry:
        entry["sandbox"].destroy()
        logger.info("沙盒已销毁: session=%s", session_id)


def destroy_all() -> None:
    """销毁所有沙盒（应用关闭时调用）。"""
    with _pool_lock:
        items = list(_sandbox_pool.items())
        _sandbox_pool.clear()
    for session_id, entry in items:
        try:
            entry["sandbox"].destroy()
        except Exception:
            pass
    if items:
        logger.info("已销毁全部沙盒: %d 个", len(items))


def pool_status() -> dict:
    """返回沙盒池状态（用于调试/监控）。"""
    with _pool_lock:
        return {
            "total": len(_sandbox_pool),
            "max": _MAX_SANDBOXES,
            "sessions": [
                {
                    "session_id": sid,
                    "container_id": e["sandbox"].container_id,
                    "idle_seconds": int(time.time() - e["last_active"]),
                }
                for sid, e in _sandbox_pool.items()
            ],
        }


def _cleanup_loop():
    """后台线程：定期清理超时的空闲沙盒。"""
    while True:
        time.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        expired_ids: list[str] = []
        with _pool_lock:
            for sid, entry in _sandbox_pool.items():
                if now - entry["last_active"] > _SANDBOX_IDLE_TIMEOUT:
                    expired_ids.append(sid)
        for sid in expired_ids:
            destroy(sid)
            logger.info("沙盒超时清理: session=%s (空闲超过 %d 秒)", sid, _SANDBOX_IDLE_TIMEOUT)


# 启动清理线程（守护线程，随主进程退出）
_cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
_cleanup_thread.start()


# ==================== 旧版 ContextVar 兼容（向后兼容） ====================
# 保留 contextvars 接口供 tools.py 中的 import 正常工作
import contextvars

_current_sandbox: contextvars.ContextVar["Sandbox | None"] = contextvars.ContextVar(
    "sandbox", default=None
)


def create() -> Sandbox:
    """[已废弃] 创建沙盒并绑定到当前上下文。请用 get_or_create(session_id)。"""
    destroy()
    sb = Sandbox()
    _current_sandbox.set(sb)
    return sb


def get() -> Sandbox | None:
    """[已废弃] 获取当前上下文的沙盒。请用 get(session_id)。"""
    return _current_sandbox.get(None)


def _quote(command: str) -> str:
    """安全的 shell 引用（单引号包裹，避免注入）。"""
    escaped = command.replace("'", "'\\''")
    return f"'{escaped}'"


def _resolve_path(path: str) -> str:
    """将相对路径转为基于 /workspace 的绝对路径。

    不做硬性约束，只做补全：
    - 相对路径如 "test.py" → "/workspace/test.py"
    - 绝对路径如 "/etc/hosts" 原样返回
    - 路径穿越（..）由 Docker 容器自身的 chroot 效果兜底
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path("/workspace") / p
    return str(p)
