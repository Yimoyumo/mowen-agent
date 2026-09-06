"""执行器抽象层：工作区执行器的统一接口。

定义：
- ExecResult: 一次执行的统一结果结构
- WorkspaceExecutor: 工作区执行器的抽象基类（宿主机 / Docker 沙盒 / 未来扩展）
- resolve_in_workspace / is_under: 工作区路径解析与信任根判断工具
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    """一次命令 / 操作执行的结构化结果。

    Attributes:
        exit_code: 退出码；命令超时或被强杀时为 -1
        output: 已截断的合并 stdout + stderr
        timed_out: 是否因超时被终止
        cancelled: 是否被外部 cancel() 显式取消（区别于超时）
        op_id: 本次执行的操作 id（uuid4().hex[:12]），供取消 / 状态查询使用
    """

    exit_code: int
    output: str
    timed_out: bool = False
    cancelled: bool = False
    op_id: str = ""


def new_op_id() -> str:
    """生成一个新的操作 id。"""
    return uuid.uuid4().hex[:12]


class WorkspaceExecutor(ABC):
    """工作区执行器抽象基类。

    一个执行器实例负责一个会话的工作区：
    - 执行 shell 命令
    - 读写文件、浏览目录
    - 导出 / 导入文件
    - 状态查询与销毁

    子类需要实现全部抽象方法，并保证线程 / 协程安全。
    """

    # ---- 生命周期 ----

    @abstractmethod
    def workspace_root(self, session_id: str) -> Path:
        """返回（并确保存在）指定会话的工作区根目录。"""

    @abstractmethod
    def destroy_session(self, session_id: str) -> None:
        """销毁指定会话的工作区资源。"""

    @abstractmethod
    def destroy_all(self) -> None:
        """销毁全部工作区资源（应用关闭时调用）。"""

    # ---- 命令执行 ----

    @abstractmethod
    async def run(
        self, session_id: str, command: str, timeout: int = 30, op_id: str | None = None
    ) -> ExecResult:
        """在工作区中执行 shell 命令。

        Args:
            op_id: 可选的预生成操作 id（供审计与取消保持一致）；不传则由实现生成。
        """

    # ---- 文件操作 ----

    @abstractmethod
    async def write_file(self, session_id: str, path: str, content: str) -> None:
        """在工作区中创建 / 覆盖文本文件。"""

    @abstractmethod
    async def write_bytes(self, session_id: str, path: str, data: bytes) -> None:
        """在工作区中写入二进制文件（如图片），供下载图片等场景使用。"""

    @abstractmethod
    async def read_file(self, session_id: str, path: str) -> str:
        """读取工作区中的文件内容。"""

    @abstractmethod
    async def read_bytes(self, session_id: str, path: str) -> bytes:
        """读取工作区中的文件原始字节（供图片查看等二进制场景）。

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件超出大小上限
        """

    @abstractmethod
    async def list_dir(self, session_id: str, path: str = "") -> str:
        """列出工作区中某个目录的内容（ls -lah 风格）。"""

    # ---- 文件导入导出 ----

    @abstractmethod
    async def export_file(self, session_id: str, path: str) -> tuple[str, str] | None:
        """将工作区文件导出到宿主机 downloads 目录。

        Returns:
            (token, filename) 元组，供 /api/download/{token}/{filename} 路由使用；
            失败时返回 None。
        """

    @abstractmethod
    async def import_file(
        self, session_id: str, host_path: str, subpath: str | None = None
    ) -> str | None:
        """将宿主机文件导入工作区。

        Args:
            host_path: 宿主机上的源文件绝对路径
            subpath: 目标文件名；不传则用源文件名

        Returns:
            工作区内的目标路径；失败时返回 None。
        """

    # ---- 状态 ----

    @abstractmethod
    def status(self) -> dict:
        """返回执行器状态（mode / running / workspace_root 等）。"""


# ==================== 工具函数 ====================


def resolve_in_workspace(workspace: Path, path: str) -> Path:
    """将路径解析为工作区内的绝对路径。

    - 相对路径 → 基于 workspace 的绝对路径
    - 绝对路径 → 原样返回（不强制约束在 workspace 内，交由调用方用 is_under 判断）

    Args:
        workspace: 工作区根目录（Path）
        path: 用户 / 工具传入的路径

    Returns:
        解析后的绝对 Path（会自动 resolve 消除符号链接 / ".."）
    """
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    return p.resolve()


def is_under(child: Path, parent: Path) -> bool:
    """判断 child 是否位于 parent 目录（含等于）之下。

    resolve 后再做前缀判断，避免符号链接绕过信任根。
    """
    try:
        child_r = child.resolve()
        parent_r = parent.resolve()
    except OSError:
        return False
    return child_r == parent_r or parent_r in child_r.parents
