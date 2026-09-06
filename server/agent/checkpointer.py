"""LangGraph Checkpointer 管理模块。

使用 SQLite 持久化 Agent 的短期记忆（消息历史 + 工具调用结果）。
检查点表与业务表共用同一个数据库文件（vector_store.dir/mowen.db），
全应用只保留一份 SQLite 数据库：

- 业务表（knowledge_bases/conversations/messages/...）— server/core/db.py 管理
- 检查点表（checkpoints/writes）— AsyncSqliteSaver.setup() 创建管理

两类连接（db.py 的每线程同步连接 + 本模块的 aiosqlite 异步连接）
通过 WAL 模式 + busy_timeout 共存于同一文件，读写不互斥。

每个会话（thread_id）对应一个独立的检查点，支持：
- 自动保存：每轮对话后自动保存完整状态（含 ToolMessage）
- 自动恢复：下次对话时自动从检查点加载历史
- 工具结果保留：ToolMessage 跨请求保留，LLM 能看到之前的工具调用结果

兼容迁移：首次启动时自动把旧版独立检查点库 data/agent_checkpoints.db
的数据合并进统一数据库，旧文件备份为 .bak（与 knowledge_bases.json
→ SQLite 迁移同一惯例）。
"""

import sqlite3

import aiosqlite
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from server.core.config import RAGConfig
from server.core.logging_config import get_logger

logger = get_logger(__name__)

# 旧版独立检查点库路径，首次启动时自动合并进统一数据库
_LEGACY_DB_PATH = Path("data/agent_checkpoints.db")

# 全局单例
_saver: AsyncSqliteSaver | None = None
_conn = None


def _get_db_path() -> Path:
    """统一数据库路径：与业务库同文件（vector_store.dir/mowen.db）。"""
    db_dir = Path(RAGConfig.from_settings().vector_store_dir)
    return db_dir / "mowen.db"


async def get_checkpointer() -> BaseCheckpointSaver:
    """获取全局 SQLite Checkpointer 单例。

    首次调用时连接统一数据库（与业务库同文件）、初始化检查点表，
    并迁移旧版独立检查点库的数据。后续调用直接返回已有实例。

    Returns:
        AsyncSqliteSaver 实例，可直接传给 create_react_agent(checkpointer=...)
    """
    global _saver, _conn

    if _saver is not None:
        return _saver

    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建异步 SQLite 连接（与 db.py 的同步连接共存，WAL 模式下读写不互斥）
    _conn = await aiosqlite.connect(str(db_path))
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA busy_timeout=5000")
    _saver = AsyncSqliteSaver(conn=_conn)

    # 初始化检查点表（幂等）
    await _saver.setup()

    # 迁移旧版独立检查点库（幂等，仅首次）
    _migrate_legacy_checkpoints(db_path)

    logger.info("Checkpointer 初始化完成: %s", db_path)
    return _saver


def _migrate_legacy_checkpoints(db_path: Path) -> None:
    """把旧版独立检查点库合并进统一数据库。

    仅当旧文件存在且统一库 checkpoints 表为空时执行，已迁移过的不重复导入。
    成功后旧文件重命名为 .bak；失败则保留原文件，下次启动重试。
    """
    if not _LEGACY_DB_PATH.exists():
        return

    copied: list[str] = []
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        count = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        if count > 0:
            logger.info("统一数据库已有检查点数据（%d 条），跳过旧库迁移: %s",
                        count, _LEGACY_DB_PATH)
            return

        conn.execute("ATTACH DATABASE ? AS legacy", (str(_LEGACY_DB_PATH),))

        target_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        }
        legacy_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM legacy.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        }

        # 迁移目标仅限 langgraph 检查点表：逐表写死静态 SQL，无任何拼接
        for table in ("checkpoints", "writes"):
            if table not in target_tables or table not in legacy_tables:
                continue
            if table == "checkpoints":
                main_cols = [r[1] for r in conn.execute("PRAGMA table_info(checkpoints)")]
                legacy_cols = [r[1] for r in conn.execute("PRAGMA legacy.table_info(checkpoints)")]
                if main_cols != legacy_cols:
                    logger.warning("检查点迁移跳过表 %s（列结构不一致）", table)
                    continue
                conn.execute("INSERT OR IGNORE INTO main.checkpoints SELECT * FROM legacy.checkpoints")
            else:
                main_cols = [r[1] for r in conn.execute("PRAGMA table_info(writes)")]
                legacy_cols = [r[1] for r in conn.execute("PRAGMA legacy.table_info(writes)")]
                if main_cols != legacy_cols:
                    logger.warning("检查点迁移跳过表 %s（列结构不一致）", table)
                    continue
                conn.execute("INSERT OR IGNORE INTO main.writes SELECT * FROM legacy.writes")
            copied.append(table)
        conn.commit()
        conn.execute("DETACH DATABASE legacy")
    except Exception:
        conn.rollback()
        logger.exception("旧检查点库迁移失败（保留原文件，下次启动重试）: %s", _LEGACY_DB_PATH)
        return
    finally:
        conn.close()

    # 收尾：将旧库 WAL 落盘后重命名为备份，避免 -wal/-shm 悬挂
    try:
        legacy_conn = sqlite3.connect(str(_LEGACY_DB_PATH))
        legacy_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        legacy_conn.close()
    except Exception:
        logger.warning("旧检查点库 WAL 落盘失败，继续重命名", exc_info=True)

    backup_path = Path(str(_LEGACY_DB_PATH) + ".bak")
    _LEGACY_DB_PATH.rename(backup_path)
    for extra in (_LEGACY_DB_PATH.with_name(_LEGACY_DB_PATH.name + "-wal"),
                  _LEGACY_DB_PATH.with_name(_LEGACY_DB_PATH.name + "-shm")):
        extra.unlink(missing_ok=True)

    logger.info("检查点已迁移至统一数据库: %s ← %s（表: %s），旧文件备份为 %s",
                db_path, _LEGACY_DB_PATH, ",".join(copied) or "无", backup_path.name)


async def close_checkpointer() -> None:
    """关闭 Checkpointer 连接。应用退出时调用。"""
    global _saver, _conn

    if _conn is not None:
        await _conn.close()
        _conn = None
        _saver = None
        logger.info("Checkpointer 已关闭")
