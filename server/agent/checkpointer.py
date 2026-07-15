"""LangGraph Checkpointer 管理模块。

使用 SQLite 持久化 Agent 的短期记忆（消息历史 + 工具调用结果）。
每个会话（thread_id）对应一个独立的检查点，支持：
- 自动保存：每轮对话后自动保存完整状态（含 ToolMessage）
- 自动恢复：下次对话时自动从检查点加载历史
- 工具结果保留：ToolMessage 跨请求保留，LLM 能看到之前的工具调用结果

数据文件：data/agent_checkpoints.db
"""

import aiosqlite
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from server.core.logging_config import get_logger

logger = get_logger(__name__)

# 检查点数据库路径
_CHECKPOINT_DB_PATH = Path("data/agent_checkpoints.db")


# 全局单例
_saver: AsyncSqliteSaver | None = None
_conn = None


async def get_checkpointer() -> BaseCheckpointSaver:
    """获取全局 SQLite Checkpointer 单例。

    首次调用时创建 AsyncSqliteSaver 并初始化数据库表。
    后续调用直接返回已有实例。

    Returns:
        AsyncSqliteSaver 实例，可直接传给 create_react_agent(checkpointer=...)
    """
    global _saver, _conn

    if _saver is not None:
        return _saver

    # 确保目录存在
    _CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 创建异步 SQLite 连接
    _conn = await aiosqlite.connect(str(_CHECKPOINT_DB_PATH))
    _saver = AsyncSqliteSaver(conn=_conn)

    # 初始化检查点表（幂等）
    await _saver.setup()

    logger.info("Checkpointer 初始化完成: %s", _CHECKPOINT_DB_PATH)
    return _saver


async def close_checkpointer() -> None:
    """关闭 Checkpointer 连接。应用退出时调用。"""
    global _saver, _conn

    if _conn is not None:
        await _conn.close()
        _conn = None
        _saver = None
        logger.info("Checkpointer 已关闭")
