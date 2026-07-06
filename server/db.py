"""数据库基础设施。

SQLite 连接管理 + 表初始化 + 迁移工具。

特性：
- 连接池：thread-safe，FastAPI 多线程安全
- WAL 模式：读写不互斥，提升并发性能
- 自动建表：首次调用 init_db() 时自动创建所有表
- JSON 迁移：从 knowledge_bases.json 自动导入旧数据

用法：
    from server.db import db

    # 应用启动时初始化
    db.init()

    # 查询
    rows = db.execute("SELECT * FROM knowledge_bases").fetchall()

    # 写入
    db.execute("INSERT INTO knowledge_bases (...) VALUES (...)")
    db.commit()
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

from server.config import RAGConfig
from server.logging_config import get_logger

logger = get_logger(__name__)

# ==================== 建表 SQL ====================

_SCHEMA = """
-- 知识库元数据
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    kb_type         TEXT DEFAULT 'general',
    collection_name TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""


class Database:
    """SQLite 数据库管理器。

    线程安全：每个线程通过 _local 获取独立的连接。
    FastAPI 的线程池中每个线程有自己的 connection，互不干扰。

    WAL 模式：读写不互斥，多个读可以并发，写仍然串行但不会阻塞读。
    """

    def __init__(self):
        self._db_path: str = ""
        self._local: threading.local = threading.local()
        self._initialized: bool = False

    def init(self, db_path: str | None = None) -> None:
        """初始化数据库，创建表结构。

        幂等操作，多次调用安全。

        Args:
            db_path: 数据库文件路径，默认从 user_settings 的 vector_store.dir 推导
        """
        if self._initialized:
            return

        if db_path is None:
            config = RAGConfig.from_settings()
            db_dir = Path(config.vector_store_dir)
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "mowen.db")

        self._db_path = db_path

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化连接（主线程）
        conn = self._get_conn()

        # 建表
        conn.executescript(_SCHEMA)
        conn.commit()

        # 从 JSON 迁移旧数据
        self._migrate_from_json()

        self._initialized = True
        logger.info("数据库已初始化: %s", db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的 SQLite 连接。

        每个线程有自己的连接，避免跨线程错误。
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,  # 我们自己管理线程隔离
            )
            # 开启 WAL 模式：读写不互斥
            conn.execute("PRAGMA journal_mode=WAL")
            # 设置超时：写冲突时等待 5 秒
            conn.execute("PRAGMA busy_timeout=5000")
            # 外键约束
            conn.execute("PRAGMA foreign_keys=ON")
            # Row Factory：查询结果像字典一样访问
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL（自动处理连接）。

        对于写操作（INSERT/UPDATE/DELETE），调用后需手动 commit()。
        对于读操作（SELECT），直接使用返回的 Cursor。

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            Cursor 对象
        """
        conn = self._get_conn()
        return conn.execute(sql, params)

    def commit(self) -> None:
        """提交当前线程的事务。"""
        conn = self._get_conn()
        conn.commit()

    def close(self) -> None:
        """关闭当前线程的连接。"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ==================== 迁移 ====================

    def _migrate_from_json(self) -> None:
        """从 knowledge_bases.json 迁移旧数据到 SQLite。

        仅在表为空时执行，已迁移过的不会重复导入。
        """
        # 检查是否已有数据
        count = self.execute("SELECT COUNT(*) FROM knowledge_bases").fetchone()[0]
        if count > 0:
            return

        # 查找旧 JSON 文件
        try:
            config = RAGConfig.from_settings()
        except Exception:
            return

        json_path = Path(config.vector_store_dir) / "knowledge_bases.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                kbs = json.load(f)
        except Exception as exc:
            logger.warning("迁移: 读取 knowledge_bases.json 失败: %s", exc)
            return

        if not kbs:
            return

        # 导入
        for kb in kbs:
            self.execute(
                """INSERT INTO knowledge_bases
                   (id, name, description, kb_type, collection_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    kb["id"],
                    kb["name"],
                    kb.get("description", ""),
                    kb.get("kb_type", "general"),
                    kb["collection_name"],
                    kb["created_at"],
                ),
            )
        self.commit()

        # 重命名旧文件为备份
        backup_path = json_path.with_suffix(".json.bak")
        json_path.rename(backup_path)
        logger.info("迁移完成: %d 条知识库从 JSON 导入 SQLite，旧文件备份为 %s",
                     len(kbs), backup_path.name)


# ==================== 全局单例 ====================

db = Database()
