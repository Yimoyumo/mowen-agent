"""执行器抽象层：统一的工作区执行接口。

为 Agent 的宿主机直操（去沙盒化）提供执行器抽象：
- get_executor: 获取当前配置对应的执行器实例（host 默认 / sandbox 回退）
- WorkspaceExecutor: 工作区执行器抽象基类
- ExecResult: 执行结果结构

Docker 沙盒保留为可切换的回退模式（沙盒模式惰性加载）。
"""

from server.agent.executor.base import ExecResult, WorkspaceExecutor
from server.agent.executor.factory import get_executor

__all__ = ["get_executor", "WorkspaceExecutor", "ExecResult"]
