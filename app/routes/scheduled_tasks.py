"""定时任务路由。

提供定时任务的 CRUD API + 执行控制。

路由：
- GET    /api/scheduled-tasks              列出所有任务
- GET    /api/scheduled-tasks/{id}         获取单个任务
- POST   /api/scheduled-tasks              创建任务
- PUT    /api/scheduled-tasks/{id}         更新任务
- DELETE /api/scheduled-tasks/{id}         删除任务
- POST   /api/scheduled-tasks/{id}/pause   暂停任务
- POST   /api/scheduled-tasks/{id}/resume  恢复任务
- POST   /api/scheduled-tasks/{id}/run     立即执行一次
- GET    /api/scheduled-tasks/{id}/conversation  获取任务对应的对话记录
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import NotFoundError, ValidationError
from server.core.logging_config import get_logger
from server.core.scheduled_task_store import task_store
from server.core.scheduler import scheduler_manager

logger = get_logger(__name__)
router = APIRouter()


# ==================== 请求模型 ====================

class CreateTaskRequest(BaseModel):
    name: str
    prompt: str
    schedule_type: str          # cron / interval / once
    schedule_config: dict        # {"expression": "0 9 * * *"} / {"seconds": 3600} / {"datetime": "2024-12-25T09:00:00"}
    kb_id: str | None = None


class UpdateTaskRequest(BaseModel):
    name: str | None = None
    prompt: str | None = None
    schedule_type: str | None = None
    schedule_config: dict | None = None
    kb_id: str | None = None


# ==================== 路由 ====================

@router.get("/scheduled-tasks")
def list_tasks() -> dict:
    """列出所有定时任务。"""
    tasks = task_store.list_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/scheduled-tasks/{task_id}")
def get_task(task_id: str) -> dict:
    """获取单个定时任务。"""
    task = task_store.get(task_id)
    if not task:
        raise NotFoundError("定时任务不存在")
    return task


@router.post("/scheduled-tasks")
async def create_task(req: CreateTaskRequest) -> dict:
    """创建定时任务。"""
    # 参数校验
    if not req.name.strip():
        raise ValidationError("任务名称不能为空")
    if not req.prompt.strip():
        raise ValidationError("提示词不能为空")
    if req.schedule_type not in ("cron", "interval", "once"):
        raise ValidationError(f"不支持的调度类型: {req.schedule_type}")

    # 校验调度配置
    _validate_schedule_config(req.schedule_type, req.schedule_config)

    task_id = uuid.uuid4().hex[:16]

    task = task_store.create(
        task_id=task_id,
        name=req.name.strip(),
        prompt=req.prompt.strip(),
        schedule_type=req.schedule_type,
        schedule_config=req.schedule_config,
        kb_id=req.kb_id,
    )

    # 添加到调度器
    scheduler_manager.add_task(task)

    # 更新下次执行时间
    next_run = scheduler_manager._get_next_run_time(task_id)
    if next_run:
        task_store.set_next_run(task_id, next_run)
        task["next_run_at"] = next_run

    logger.info("定时任务已创建: id=%s name=%s", task_id, req.name)
    return task


@router.put("/scheduled-tasks/{task_id}")
async def update_task(task_id: str, req: UpdateTaskRequest) -> dict:
    """更新定时任务。"""
    existing = task_store.get(task_id)
    if not existing:
        raise NotFoundError("定时任务不存在")

    # 校验调度配置
    sch_type = req.schedule_type or existing["schedule_type"]
    sch_config = req.schedule_config or existing["schedule_config"]
    _validate_schedule_config(sch_type, sch_config)

    updates = {}
    if req.name is not None:
        updates["name"] = req.name.strip()
    if req.prompt is not None:
        updates["prompt"] = req.prompt.strip()
    if req.schedule_type is not None:
        updates["schedule_type"] = req.schedule_type
    if req.schedule_config is not None:
        updates["schedule_config"] = req.schedule_config
    if req.kb_id is not None:
        updates["kb_id"] = req.kb_id

    task_store.update(task_id, **updates)

    # 重新调度
    updated_task = task_store.get(task_id)
    if updated_task and updated_task["status"] == "active":
        scheduler_manager.add_task(updated_task)
        next_run = scheduler_manager._get_next_run_time(task_id)
        if next_run:
            task_store.set_next_run(task_id, next_run)
            updated_task["next_run_at"] = next_run

    logger.info("定时任务已更新: id=%s", task_id)
    return updated_task


@router.delete("/scheduled-tasks/{task_id}")
def delete_task(task_id: str) -> dict:
    """删除定时任务。"""
    existing = task_store.get(task_id)
    if not existing:
        raise NotFoundError("定时任务不存在")

    scheduler_manager.remove_task(task_id)
    task_store.delete(task_id)
    logger.info("定时任务已删除: id=%s", task_id)
    return {"status": "ok"}


@router.post("/scheduled-tasks/{task_id}/pause")
def pause_task(task_id: str) -> dict:
    """暂停定时任务。"""
    existing = task_store.get(task_id)
    if not existing:
        raise NotFoundError("定时任务不存在")

    scheduler_manager.pause_task(task_id)
    task_store.update(task_id, status="paused")
    logger.info("定时任务已暂停: id=%s", task_id)
    return {"status": "ok"}


@router.post("/scheduled-tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict:
    """恢复定时任务。"""
    existing = task_store.get(task_id)
    if not existing:
        raise NotFoundError("定时任务不存在")

    task = task_store.get(task_id)
    task_store.update(task_id, status="active")
    updated = task_store.get(task_id)
    scheduler_manager.resume_task(task_id, updated)
    next_run = scheduler_manager._get_next_run_time(task_id)
    if next_run:
        task_store.set_next_run(task_id, next_run)
        updated["next_run_at"] = next_run

    logger.info("定时任务已恢复: id=%s", task_id)
    return updated


@router.post("/scheduled-tasks/{task_id}/run")
async def run_task_now(task_id: str) -> dict:
    """立即执行一次（不影响调度计划）。"""
    existing = task_store.get(task_id)
    if not existing:
        raise NotFoundError("定时任务不存在")

    # 异步执行，不阻塞响应
    import asyncio
    asyncio.create_task(scheduler_manager._execute_task(task_id))

    logger.info("定时任务手动触发: id=%s", task_id)
    return {"status": "ok", "message": "任务已触发"}


@router.get("/scheduled-tasks/{task_id}/conversation")
def get_task_conversation(task_id: str) -> dict:
    """获取定时任务对应的对话记录。"""
    from server.core.conversation_store import conv_store

    conv_id = f"scheduled_{task_id}"
    conv = conv_store.get_conversation(conv_id)
    if not conv:
        return {"conversation": None, "messages": []}
    return conv


# ==================== 工具函数 ====================

def _validate_schedule_config(schedule_type: str, config: dict) -> None:
    """校验调度配置参数。"""
    if schedule_type == "cron":
        expr = config.get("expression", "").strip()
        if not expr:
            raise ValidationError("cron 任务需要 expression 字段")
        # 简单校验：cron 表达式应有 5 个字段
        parts = expr.split()
        if len(parts) != 5:
            raise ValidationError("cron 表达式需要 5 个字段 (分 时 日 月 周)")

    elif schedule_type == "interval":
        seconds = config.get("seconds", 0)
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise ValidationError("interval 任务需要正数 seconds 字段")

    elif schedule_type == "once":
        dt_str = config.get("datetime", "").strip()
        if not dt_str:
            raise ValidationError("once 任务需要 datetime 字段")
        # 校验 ISO 格式
        from datetime import datetime
        try:
            datetime.fromisoformat(dt_str)
        except ValueError:
            raise ValidationError("datetime 格式无效，应为 ISO 8601 格式 (如 2024-12-25T09:00:00)")
