"""执行器工厂：根据配置返回合适的 WorkspaceExecutor 实例。

- host 模式（默认）：HostExecutor，直接在宿主机执行
- sandbox 模式：SandboxExecutor 适配器，包装现有 Docker 沙盒

沙盒适配器惰性导入（函数内 import），保证 host 模式下不装 Docker SDK 依赖也能正常运行。
"""

from __future__ import annotations

from server.core.logging_config import get_logger
from server.agent.executor.base import WorkspaceExecutor

logger = get_logger(__name__)

_executor: WorkspaceExecutor | None = None
_executor_mode: str | None = None
_executor_config: dict | None = None


def get_executor(config=None) -> WorkspaceExecutor:
    """获取执行器实例（单例缓存）。

    Args:
        config: RAGConfig 实例；为 None 时使用默认 host 模式。
            从 config.executor_mode 读取模式（host 默认 / sandbox），
            从 config.executor_config 读取执行器配置。

    当缓存的实例类型 / 配置与请求不一致时自动重建。
    """
    global _executor, _executor_mode, _executor_config

    mode = "host"
    ex_config: dict = {}
    if config is not None:
        mode = getattr(config, "executor_mode", "host") or "host"
        ex_config = dict(getattr(config, "executor_config", None) or {})

    if _executor is not None and _executor_mode == mode and _executor_config == ex_config:
        return _executor

    if mode == "sandbox":
        # 惰性导入：仅 sandbox 模式才加载 Docker SDK 相关依赖
        from server.agent.executor.sandbox import SandboxExecutor

        _executor = SandboxExecutor(ex_config)
    else:
        from server.agent.executor.host import HostExecutor

        _executor = HostExecutor(ex_config)

    _executor_mode = mode
    _executor_config = ex_config
    logger.info("执行器已初始化: mode=%s", mode)
    return _executor
