"""定时任务持久化存储。

基于 SQLite 存储定时任务定义，支持：
- CRUD：创建/查询/更新/删除定时任务
- 状态管理：active / paused / completed / error
- 执行记录：last_run_at / next_run_at / run_count / last_result

用法：
    from server.core.scheduled_task_store import task_store

    task_store.create({...})
    task_store.list_tasks()
    task_store.update_status(id, "paused")
"""

import json
import sqlite3
import time

from server.core.db import db
from server.core.logging_config import get_logger

logger = get_logger(__name__)


def _row_to_task(row: sqlite3.Row) -> dict:
    """将 scheduled_tasks 表的行转为字典。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "prompt": row["prompt"],
        "schedule_type": row["schedule_type"],
        "schedule_config": json.loads(row["schedule_config"] or "{}"),
        "kb_id": row["kb_id"],
        "status": row["status"],
        "last_run_at": row["last_run_at"],
        "next_run_at": row["next_run_at"],
        "last_result": row["last_result"] or "",
        "run_count": row["run_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class ScheduledTaskStore:
    """定时任务存储管理器。"""

    def create(self, task_id: str, name: str, prompt: str,
               schedule_type: str, schedule_config: dict,
               kb_id: str | None = None) -> dict:
        """创建定时任务。"""
        now = int(time.time() * 1000)
        db.execute(
            """INSERT INTO scheduled_tasks
               (id, name, prompt, schedule_type, schedule_config, kb_id,
                status, last_run_at, next_run_at, last_result, run_count,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, NULL, '', 0, ?, ?)""",
            (task_id, name, prompt, schedule_type,
             json.dumps(schedule_config, ensure_ascii=False), kb_id, now, now),
        )
        db.commit()
        return self.get(task_id)

    def get(self, task_id: str) -> dict | None:
        """获取单个定时任务。"""
        row = db.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(self) -> list[dict]:
        """列出所有定时任务，按创建时间倒序。"""
        rows = db.execute(
            "SELECT * FROM scheduled_tasks ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def list_active_tasks(self) -> list[dict]:
        """列出所有活跃状态的任务（含 active 和 error）。"""
        rows = db.execute(
            "SELECT * FROM scheduled_tasks WHERE status IN ('active', 'error') ORDER BY next_run_at ASC"
        ).fetchall()
        return [_row_to_task(r) for r in rows]

    def update(self, task_id: str, **fields) -> bool:
        """更新任务字段，支持 name, prompt, schedule_type, schedule_config, kb_id, status。"""
        now = int(time.time() * 1000)
        allowed = {"name", "prompt", "schedule_type", "schedule_config", "kb_id", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False

        # schedule_config 需要 JSON 序列化
        if "schedule_config" in updates and isinstance(updates["schedule_config"], dict):
            updates["schedule_config"] = json.dumps(updates["schedule_config"], ensure_ascii=False)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [now, task_id]
        db.execute(
            f"UPDATE scheduled_tasks SET {set_clause}, updated_at = ? WHERE id = ?",
            values,
        )
        db.commit()
        return True

    def update_run_result(self, task_id: str, result: str,
                         next_run_at: int | None = None,
                         status: str | None = None) -> None:
        """更新任务执行结果。"""
        now = int(time.time() * 1000)
        fields = ["last_run_at = ?", "last_result = ?", "run_count = run_count + 1", "updated_at = ?"]
        values: list = [now, result[:500], now]

        if next_run_at is not None:
            fields.append("next_run_at = ?")
            values.append(next_run_at)
        if status is not None:
            fields.append("status = ?")
            values.append(status)

        values.append(task_id)
        set_clause = ", ".join(fields)
        db.execute(
            f"UPDATE scheduled_tasks SET {set_clause} WHERE id = ?",
            values,
        )
        db.commit()

    def set_next_run(self, task_id: str, next_run_at: int | None) -> None:
        """设置下次执行时间。"""
        now = int(time.time() * 1000)
        db.execute(
            "UPDATE scheduled_tasks SET next_run_at = ?, updated_at = ? WHERE id = ?",
            (next_run_at, now, task_id),
        )
        db.commit()

    def delete(self, task_id: str) -> bool:
        """删除定时任务。"""
        cur = db.execute(
            "DELETE FROM scheduled_tasks WHERE id = ?", (task_id,)
        )
        db.commit()
        return cur.rowcount > 0


task_store = ScheduledTaskStore()
