"""宿主操作审计：记录 Agent 在宿主机上的命令 / 文件 / 审批操作。

数据写入 SQLite 的 host_ops 表（见 server/core/db.py 的 _SCHEMA）。
- record(): 按 op_id 插入或更新（幂等，WAL 小写入，同步调用即可）。
- list_ops(): 列出操作记录（可按 session_id 过滤，分页）。
- running_ops(): 列出运行中 / 待审批的操作。
"""

from __future__ import annotations

import time
from pathlib import Path

from server.core.db import db
from server.core.logging_config import get_logger

logger = get_logger(__name__)

_OUTPUT_DIGEST_LIMIT = 2000  # 输出摘要截断长度（字符）

# status 取值说明（与前端 HostOpsPanel 对齐）：
# pending_approval / approved / denied / timeout / running / succeeded / failed / killed
_RUNNING_STATUSES = ("running", "pending_approval")


def _digest(output: str) -> str:
    """截断输出摘要。"""
    if not output:
        return ""
    return output[:_OUTPUT_DIGEST_LIMIT]


def record(entry: dict) -> None:
    """插入或更新一条宿主操作审计记录。

    Args:
        entry: 含以下字段的 dict：
            op_id, session_id, tool, kind, target, risk, status,
            可选 exit_code / output / finished_at。
            缺少 created_at 时自动填充当前时间戳。
    """
    op_id = entry.get("op_id", "")
    if not op_id:
        logger.warning("审计记录缺少 op_id，跳过: %s", entry)
        return
    session_id = entry.get("session_id", "")
    tool = entry.get("tool", "")
    kind = entry.get("kind", "")
    target = entry.get("target", "")
    risk = entry.get("risk", "")
    status = entry.get("status", "")
    exit_code = entry.get("exit_code")
    output_digest = _digest(entry.get("output", ""))
    created_at = entry.get("created_at") or int(time.time())
    finished_at = entry.get("finished_at")

    try:
        # 存在则更新，否则插入（按 op_id 幂等）
        existing = db.execute(
            "SELECT id FROM host_ops WHERE op_id = ?", (op_id,)
        ).fetchone()
        if existing:
            db.execute(
                """UPDATE host_ops SET session_id=?, tool=?, kind=?, target=?,
                   risk=?, status=?, exit_code=?, output_digest=?, finished_at=?
                   WHERE op_id=?""",
                (
                    session_id, tool, kind, target, risk, status,
                    exit_code, output_digest, finished_at, op_id,
                ),
            )
        else:
            db.execute(
                """INSERT INTO host_ops
                   (op_id, session_id, tool, kind, target, risk, status,
                    exit_code, output_digest, created_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    op_id, session_id, tool, kind, target, risk, status,
                    exit_code, output_digest, created_at, finished_at,
                ),
            )
        db.commit()
    except Exception as exc:
        logger.error("写入 host_ops 审计失败: op_id=%s err=%s", op_id, exc)


def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def list_ops(session_id: str | None = None, limit: int = 50) -> list[dict]:
    """列出宿主操作记录，按创建时间倒序。

    Args:
        session_id: 只返回该会话；None 返回全部。
        limit: 返回条数上限。
    """
    limit = max(1, min(int(limit or 50), 500))
    try:
        if session_id:
            rows = db.execute(
                "SELECT * FROM host_ops WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM host_ops ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("读取 host_ops 失败: %s", exc)
        return []


def running_ops(session_id: str | None = None) -> list[dict]:
    """列出运行中 / 待审批的操作。

    Args:
        session_id: 只返回该会话；None 返回全部。
    """
    placeholders = ",".join("?" for _ in _RUNNING_STATUSES)
    try:
        if session_id:
            rows = db.execute(
                f"SELECT * FROM host_ops WHERE session_id=? AND status IN ({placeholders}) "
                "ORDER BY created_at DESC",
                (session_id, *_RUNNING_STATUSES),
            ).fetchall()
        else:
            rows = db.execute(
                f"SELECT * FROM host_ops WHERE status IN ({placeholders}) "
                "ORDER BY created_at DESC",
                _RUNNING_STATUSES,
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("读取 running_ops 失败: %s", exc)
        return []


def set_output_digest(op_id: str, output: str) -> None:
    """更新操作的输出摘要（进程结束后回填）。"""
    try:
        db.execute(
            "UPDATE host_ops SET output_digest=? WHERE op_id=?",
            (_digest(output), op_id),
        )
        db.commit()
    except Exception as exc:
        logger.warning("更新 output_digest 失败: op_id=%s err=%s", op_id, exc)
