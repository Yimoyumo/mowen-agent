"""Docker 沙盒管理器。

为 Agent 提供一个可持久操控的 Linux 环境：
- 执行任意 shell 命令（含 pip install、编译等）
- 读写文件、浏览目录
- 容器在对话开始时创建，结束时销毁
- 通过 contextvars 在线程/协程间传递沙盒引用
- export_file: 将容器内文件导出到宿主机供用户下载
"""

import contextvars
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import docker
from docker.errors import DockerException, NotFound

_SANDBOX_IMAGE = "mowen-sandbox:latest"  # 优先用自建镜像（预装工具），不存在时回退到 python:3.12-slim
_SANDBOX_MEMORY = "512m"
_SANDBOX_CPU = 1.0
_DEFAULT_TIMEOUT = 60          # 默认命令超时（秒）

_DOWNLOADS_DIR = Path("downloads")  # 文件导出目录
_UPLOADS_DIR = Path("uploads")      # 用户上传暂存目录

_current_sandbox: contextvars.ContextVar["Sandbox | None"] = contextvars.ContextVar(
    "sandbox", default=None
)


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
        # 用 shell heredoc 写入文件
        safe_content = content.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")
        cmd = f"cat > {_safe_path(path)} << 'SANDBOX_EOF'\n{safe_content}\nSANDBOX_EOF"
        self.exec(cmd)

    def read_file(self, path: str) -> str:
        """读取沙盒中的文件内容。"""
        exit_code, output = self.exec(f"cat {_safe_path(path)}")
        if exit_code != 0:
            return f"（文件不存在或无法读取: {path}）"
        return output

    def list_dir(self, path: str = "/workspace") -> str:
        """列出目录内容（ls -lah）。"""
        exit_code, output = self.exec(f"ls -lah {_safe_path(path)}")
        if exit_code != 0:
            return f"（目录不存在或无法列出: {path}）"
        return output

    def export_file(self, container_path: str) -> tuple[str, str] | None:
        """将容器内文件导出到宿主机 downloads 目录。

        Args:
            container_path: 容器内文件路径

        Returns:
            (download_token, filename) 元组，供构造下载 URL
            失败返回 None
        """
        safe = _safe_path(container_path)
        # 确保目标目录存在
        _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        filename = Path(safe).name
        token = str(uuid.uuid4())[:8]
        dest_dir = _DOWNLOADS_DIR / token
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        try:
            cp_result = subprocess.run(
                ["docker", "cp", f"{self._container.id}:{safe}", str(dest_path)],
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
        """将宿主机文件导入沙盒容器。

        Args:
            host_path: 宿主机上的文件绝对路径
            container_subpath: 容器内的目标路径（相对于 /workspace），默认用原文件名

        Returns:
            容器内的文件路径，失败返回 None
        """
        src = Path(host_path)
        if not src.is_file():
            return None

        filename = container_subpath or src.name
        dest = _safe_path(f"/workspace/{filename}")

        try:
            cp_result = subprocess.run(
                ["docker", "cp", str(src), f"{self._container.id}:{dest}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if cp_result.returncode != 0:
                return None
            return f"/workspace/{Path(dest).name}"
        except Exception:
            return None

    def destroy(self) -> None:
        """销毁沙盒容器。"""
        try:
            self._container.remove(force=True)
        except (NotFound, Exception):
            pass


# ==================== 全局生命周期 ====================


def create() -> Sandbox:
    """创建新的沙盒实例并绑定到当前上下文。"""
    destroy()  # 先清理旧的
    sb = Sandbox()
    _current_sandbox.set(sb)
    return sb


def get() -> Sandbox | None:
    """获取当前上下文的沙盒实例。"""
    return _current_sandbox.get(None)


def destroy() -> None:
    """销毁当前上下文的沙盒实例。"""
    sb = _current_sandbox.get(None)
    if sb:
        sb.destroy()
        _current_sandbox.set(None)


def _quote(command: str) -> str:
    """安全的 shell 引用（单引号包裹，避免注入）。"""
    escaped = command.replace("'", "'\\''")
    return f"'{escaped}'"


def _safe_path(path: str) -> str:
    """防止路径穿越，将路径约束在 /workspace 内。"""
    p = Path(path)
    if not p.is_absolute():
        p = Path("/workspace") / p
    # 解析 .. 并确保在 /workspace 内
    resolved = p.resolve()
    if str(resolved).startswith("/workspace"):
        return str(resolved)
    return "/workspace/" + resolved.name
