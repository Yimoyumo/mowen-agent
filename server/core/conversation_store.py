"""对话历史持久化存储。

基于 SQLite 存储对话会话和消息，支持：
- CRUD：创建/查询/删除会话
- 消息增删改：单条消息的追加、更新、删除
- 批量同步：前端 localStorage → 后端一次性导入

数据流：
    前端 chat store ←→ API ←→ conversation_store ←→ SQLite

用法：
    from server.core.conversation_store import conv_store

    conv_store.create_conversation("abc123", "新对话")
    conv_store.add_message("abc123", {"id": "msg1", "role": "user", ...})
    conv_store.list_conversations()
"""

import json
import sqlite3
from typing import Any

from server.core.db import db
from server.core.logging_config import get_logger

logger = get_logger(__name__)


def _row_to_conv(row: sqlite3.Row) -> dict:
    """将 conversations 表的行转为字典。"""
    return {
        "id": row["id"],
        "title": row["title"],
        "kbId": row["kb_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _row_to_msg(row: sqlite3.Row) -> dict:
    """将 messages 表的行转为字典。"""
    def _safe_json(raw: str, field: str, msg_id: str) -> list:
        """安全解析 JSON 字段，失败时返回空列表并记录警告。"""
        if not raw:
            return []
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except json.JSONDecodeError:
            logger.warning("消息 JSON 字段解析失败: msg=%s field=%s value=%.80s", msg_id, field, raw)
            return []

    msg_id = row["id"]
    return {
        "id": msg_id,
        "role": row["role"],
        "content": row["content"],
        "reasoning": row["reasoning"] or "",
        "contexts": _safe_json(row["contexts"], "contexts", msg_id),
        "segments": _safe_json(row["segments"], "segments", msg_id),
        "files": _safe_json(row["files"], "files", msg_id),
        "createdAt": row["created_at"],
    }


class ConversationStore:
    """对话历史存储管理器。"""

    # ==================== 会话操作 ====================

    def create_conversation(self, conv_id: str, title: str = "新对话",
                            kb_id: str | None = None,
                            created_at: int | None = None,
                            updated_at: int | None = None) -> dict:
        """创建新会话。已存在则更新。"""
        import time
        now = int(time.time() * 1000)
        created_at = created_at or now
        updated_at = updated_at or now

        db.execute(
            """INSERT INTO conversations (id, title, kb_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,
                 kb_id=excluded.kb_id,
                 updated_at=excluded.updated_at""",
            (conv_id, title, kb_id, created_at, updated_at),
        )
        db.commit()
        return {
            "id": conv_id, "title": title, "kbId": kb_id,
            "createdAt": created_at, "updatedAt": updated_at,
        }

    def list_conversations(self, since: int | None = None) -> list[dict]:
        """列出所有会话（不含消息），按更新时间倒序。

        Args:
            since: 可选，只返回 updated_at > since 的会话（用于增量同步）
        """
        if since is not None:
            rows = db.execute(
                "SELECT * FROM conversations WHERE updated_at > ? ORDER BY updated_at DESC",
                (since,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [_row_to_conv(r) for r in rows]

    def get_conversation(self, conv_id: str) -> dict | None:
        """获取单个会话及其所有消息。"""
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            return None

        conv = _row_to_conv(row)
        msg_rows = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,),
        ).fetchall()
        conv["messages"] = [_row_to_msg(r) for r in msg_rows]
        return conv

    def update_conversation(self, conv_id: str, title: str | None = None,
                            kb_id: str | None = None) -> None:
        """更新会话标题或知识库。"""
        import time
        now = int(time.time() * 1000)
        if title is not None:
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, conv_id),
            )
        if kb_id is not None:
            db.execute(
                "UPDATE conversations SET kb_id = ?, updated_at = ? WHERE id = ?",
                (kb_id, now, conv_id),
            )
        db.commit()

    def delete_conversation(self, conv_id: str) -> bool:
        """删除会话及其所有消息（级联删除）。"""
        cur = db.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        db.commit()
        return cur.rowcount > 0

    def delete_all(self) -> int:
        """清空所有会话和消息。"""
        db.execute("DELETE FROM messages")
        db.execute("DELETE FROM conversations")
        db.commit()
        return 0

    # ==================== 消息操作 ====================

    def add_message(self, conv_id: str, msg: dict) -> dict:
        """添加一条消息到指定会话。"""
        msg_id = msg.get("id", "")
        db.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, reasoning, contexts, segments, files, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 content=excluded.content,
                 reasoning=excluded.reasoning,
                 contexts=excluded.contexts,
                 segments=excluded.segments,
                 files=excluded.files""",
            (
                msg_id,
                conv_id,
                msg.get("role", "user"),
                msg.get("content", ""),
                msg.get("reasoning", ""),
                json.dumps(msg.get("contexts", []), ensure_ascii=False),
                json.dumps(msg.get("segments", []), ensure_ascii=False),
                json.dumps(msg.get("files", []), ensure_ascii=False),
                msg.get("createdAt", 0),
            ),
        )
        # 更新会话的 updated_at
        import time
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (int(time.time() * 1000), conv_id),
        )
        db.commit()
        return msg

    def update_message(self, conv_id: str, msg_id: str, updates: dict) -> bool:
        """更新消息的部分字段。"""
        # 读取已有消息，合并更新
        row = db.execute(
            "SELECT * FROM messages WHERE id = ? AND conversation_id = ?",
            (msg_id, conv_id),
        ).fetchone()
        if not row:
            return False

        # 可更新字段
        old_contexts = json.loads(row["contexts"] or "[]") if row["contexts"] else []
        old_segments = json.loads(row["segments"] or "[]") if row["segments"] else []
        old_files = json.loads(row["files"] or "[]") if row["files"] else []
        fields = {
            "content": updates.get("content", row["content"]),
            "reasoning": updates.get("reasoning", row["reasoning"]),
            "contexts": json.dumps(updates.get("contexts", old_contexts), ensure_ascii=False),
            "segments": json.dumps(updates.get("segments", old_segments), ensure_ascii=False),
            "files": json.dumps(updates.get("files", old_files), ensure_ascii=False),
        }

        db.execute(
            """UPDATE messages SET
                 content = ?, reasoning = ?, contexts = ?, segments = ?, files = ?
               WHERE id = ? AND conversation_id = ?""",
            (
                fields["content"], fields["reasoning"],
                fields["contexts"], fields["segments"], fields["files"],
                msg_id, conv_id,
            ),
        )
        db.commit()
        return True

    def delete_message(self, conv_id: str, msg_id: str) -> bool:
        """删除单条消息。"""
        cur = db.execute(
            "DELETE FROM messages WHERE id = ? AND conversation_id = ?",
            (msg_id, conv_id),
        )
        db.commit()
        return cur.rowcount > 0

    def get_messages(self, conv_id: str) -> list[dict]:
        """获取指定会话的所有消息。"""
        rows = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,),
        ).fetchall()
        return [_row_to_msg(r) for r in rows]

    # ==================== 批量操作 ====================

    def batch_sync(self, conversations: list[dict]) -> dict:
        """批量同步：从前端 localStorage 导入所有会话和消息。

        策略：UPSERT（存在则更新，不存在则插入）。
        整个操作在单个事务中执行：中途任何错误都会全部回滚，保证原子性。
        适用于首次启用后端持久化时的一次性导入。

        Returns:
            {"synced_conversations": int, "synced_messages": int}
        """
        import time
        conv_count = 0
        msg_count = 0

        with db.transaction() as conn:
            for conv in conversations:
                now = int(time.time() * 1000)
                created_at = conv.get("createdAt") or now
                updated_at = conv.get("updatedAt") or now

                # 写会话（UPSERT）
                conn.execute(
                    """INSERT INTO conversations (id, title, kb_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title,
                         kb_id=excluded.kb_id,
                         updated_at=excluded.updated_at""",
                    (conv["id"], conv.get("title", "新对话"), conv.get("kbId"),
                     created_at, updated_at),
                )
                conv_count += 1

                # 写消息（UPSERT，不走 add_message 避免多次 commit）
                for msg in conv.get("messages", []):
                    conn.execute(
                        """INSERT INTO messages
                           (id, conversation_id, role, content, reasoning, contexts, segments, files, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                             content=excluded.content,
                             reasoning=excluded.reasoning,
                             contexts=excluded.contexts,
                             segments=excluded.segments,
                             files=excluded.files""",
                        (
                            msg.get("id", ""),
                            conv["id"],
                            msg.get("role", "user"),
                            msg.get("content", ""),
                            msg.get("reasoning", ""),
                            json.dumps(msg.get("contexts", []), ensure_ascii=False),
                            json.dumps(msg.get("segments", []), ensure_ascii=False),
                            json.dumps(msg.get("files", []), ensure_ascii=False),
                            msg.get("createdAt", 0),
                        ),
                    )
                    msg_count += 1

        logger.info("批量同步完成: %d 会话, %d 消息", conv_count, msg_count)
        return {"synced_conversations": conv_count, "synced_messages": msg_count}


# ==================== 全局单例 ====================

conv_store = ConversationStore()
