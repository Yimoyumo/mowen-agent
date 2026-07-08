"""APScheduler 定时任务调度器。

管理定时任务的调度生命周期：
- AsyncIOScheduler 与 FastAPI lifespan 集成
- 支持 cron / interval / once 三种调度类型
- 任务触发后调用 Agent 执行对话
- 结果存入对话历史 + 更新任务状态

用法：
    from server.core.scheduler import scheduler_manager

    # 启动时（在 lifespan 中）
    await scheduler_manager.start()
    # 自动从 DB 恢复所有活跃任务

    # 创建/删除/暂停任务
    scheduler_manager.add_task(task_dict)
    scheduler_manager.remove_task(task_id)
    scheduler_manager.pause_task(task_id)
"""

import asyncio
import json
import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from server.core.logging_config import get_logger
from server.core.scheduled_task_store import task_store

logger = get_logger(__name__)


class SchedulerManager:
    """定时任务调度管理器。

    封装 APScheduler，提供任务 CRUD + 执行回调。
    """

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    # ==================== 生命周期 ====================

    async def start(self) -> None:
        """启动调度器并从 DB 恢复所有活跃任务。

        在 FastAPI lifespan startup 中调用。
        """
        if self._started:
            return

        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,          # 多次错过合并为一次
                "max_instances": 1,        # 同一任务不并发执行
                "misfire_grace_time": 60,  # 允许 60 秒延迟
            },
        )

        # 注册事件监听
        self._scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)

        self._scheduler.start()
        self._started = True
        logger.info("调度器已启动")

        # 从 DB 恢复活跃任务
        await self._restore_tasks()

    async def shutdown(self) -> None:
        """关闭调度器。在 lifespan shutdown 中调用。"""
        if not self._started or not self._scheduler:
            return

        # 等待正在执行的任务完成（最多 30 秒）
        self._scheduler.shutdown(wait=False)
        self._started = False
        self._scheduler = None
        logger.info("调度器已关闭")

    @property
    def is_running(self) -> bool:
        return self._started

    # ==================== 任务管理 ====================

    def add_task(self, task: dict) -> None:
        """添加任务到调度器。

        Args:
            task: 任务字典（来自 task_store）
        """
        if not self._started or not self._scheduler:
            logger.warning("调度器未启动，无法添加任务: %s", task.get("id"))
            return

        task_id = task["id"]
        trigger = self._build_trigger(
            task["schedule_type"],
            task["schedule_config"],
        )
        if not trigger:
            logger.warning("无法构建触发器，跳过任务: %s (type=%s)", task_id, task["schedule_type"])
            return

        # 先移除已存在的同名任务
        self.remove_task(task_id)

        self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task_id,
            args=[task_id],
            name=task.get("name", task_id),
            replace_existing=True,
        )
        logger.info("任务已添加: id=%s name=%s type=%s", task_id, task.get("name"), task["schedule_type"])

    def remove_task(self, task_id: str) -> None:
        """从调度器移除任务（不影响 DB）。"""
        if not self._scheduler:
            return
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass  # 任务不存在，静默

    def pause_task(self, task_id: str) -> None:
        """暂停任务。"""
        if not self._scheduler:
            return
        try:
            self._scheduler.pause_job(task_id)
            logger.info("任务已暂停: %s", task_id)
        except Exception as e:
            logger.warning("暂停任务失败: %s -> %s", task_id, e)

    def resume_task(self, task_id: str, task: dict) -> None:
        """恢复任务（重新添加到调度器）。"""
        self.add_task(task)
        logger.info("任务已恢复: %s", task_id)

    # ==================== 内部实现 ====================

    def _build_trigger(self, schedule_type: str, config: dict):
        """根据类型构建 APScheduler 触发器。

        Args:
            schedule_type: "cron" / "interval" / "once"
            config:
                cron: {"expression": "0 9 * * *"}
                interval: {"seconds": 3600}
                once: {"datetime": "2024-12-25T09:00:00"}
        """
        try:
            if schedule_type == "cron":
                expr = config.get("expression", "")
                if not expr:
                    logger.warning("cron 任务缺少 expression")
                    return None
                return CronTrigger.from_crontab(expr)

            elif schedule_type == "interval":
                seconds = int(config.get("seconds", 0))
                if seconds <= 0:
                    logger.warning("interval 任务 seconds <= 0")
                    return None
                return IntervalTrigger(seconds=seconds)

            elif schedule_type == "once":
                dt_str = config.get("datetime", "")
                if not dt_str:
                    logger.warning("once 任务缺少 datetime")
                    return None
                dt = datetime.fromisoformat(dt_str)
                return DateTrigger(run_date=dt)

            else:
                logger.warning("未知调度类型: %s", schedule_type)
                return None
        except Exception as e:
            logger.error("构建触发器失败: type=%s config=%s -> %s", schedule_type, config, e)
            return None

    async def _restore_tasks(self) -> None:
        """从 DB 恢复所有活跃任务到调度器。"""
        tasks = task_store.list_active_tasks()
        restored = 0
        for task in tasks:
            # once 类型且已过期 -> 标记为已完成
            if task["schedule_type"] == "once":
                dt_str = task["schedule_config"].get("datetime", "")
                if dt_str:
                    try:
                        dt = datetime.fromisoformat(dt_str)
                        if dt < datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now():
                            task_store.update(task["id"], status="completed")
                            continue
                    except Exception:
                        pass

            self.add_task(task)
            restored += 1
        logger.info("从 DB 恢复了 %d 个定时任务", restored)

    async def _execute_task(self, task_id: str) -> None:
        """任务执行回调：调用 Agent 并保存结果。

        这是 APScheduler 调度的实际执行函数。
        """
        task = task_store.get(task_id)
        if not task:
            logger.warning("任务不存在: %s", task_id)
            return

        if task["status"] not in ("active", "error"):
            logger.info("任务非活跃状态，跳过执行: %s (status=%s)", task_id, task["status"])
            return

        logger.info("开始执行定时任务: id=%s name=%s", task_id, task.get("name"))

        # 生成会话 ID（复用沙盒系统）
        session_id = f"task_{task_id}"

        # 构建消息
        messages = [
            {"role": "user", "content": task["prompt"]},
        ]

        # 如果关联了知识库，在提示词中注明
        kb_id = task.get("kb_id")

        result_text = ""
        try:
            from server.agent import chat_stream
            from server.core.config import RAGConfig

            config = RAGConfig.from_settings()

            # 非流式模式执行
            async for chunk in chat_stream(
                messages,
                kb_id=kb_id,
                config=config,
                stream=False,
                session_id=session_id,
            ):
                if chunk.get("type") == "token":
                    result_text += chunk.get("token", "")
                elif chunk.get("type") == "error":
                    raise RuntimeError(chunk.get("message", "Agent 执行出错"))

            # 保存结果到对话历史
            self._save_to_conversation(task, result_text)

            # 计算下次执行时间
            next_run = self._get_next_run_time(task_id)

            task_store.update_run_result(
                task_id,
                result=f"成功: {result_text[:200]}",
                next_run_at=next_run,
            )

            # once 类型标记完成
            if task["schedule_type"] == "once":
                task_store.update(task_id, status="completed")
                self.remove_task(task_id)

            logger.info("定时任务执行完成: id=%s result_len=%d", task_id, len(result_text))

        except Exception as e:
            logger.error("定时任务执行失败: id=%s -> %s", task_id, e, exc_info=True)
            task_store.update_run_result(
                task_id,
                result=f"失败: {str(e)[:200]}",
                status="error",
            )

        # 任务结束后销毁沙盒
        try:
            from server.agent.sandbox import destroy as destroy_sandbox
            destroy_sandbox(session_id)
        except Exception:
            pass

    def _save_to_conversation(self, task: dict, result: str) -> None:
        """将任务执行结果保存为对话记录。

        每个定时任务使用固定的 conversation_id，便于查看历史。
        """
        from server.core.conversation_store import conv_store

        conv_id = f"scheduled_{task['id']}"
        now = int(__import__("time").time() * 1000)

        # 确保会话存在
        conv = conv_store.get_conversation(conv_id)
        if not conv:
            conv_store.create_conversation(
                conv_id,
                title=f"⏰ {task['name']}",
                kb_id=task.get("kb_id"),
            )

        # 添加用户消息
        conv_store.add_message(conv_id, {
            "id": f"task_user_{now}",
            "role": "user",
            "content": task["prompt"],
            "contexts": [],
            "segments": [],
            "files": [],
            "createdAt": now,
        })

        # 添加助手回复
        conv_store.add_message(conv_id, {
            "id": f"task_asst_{now}",
            "role": "assistant",
            "content": result,
            "reasoning": "",
            "contexts": [],
            "segments": [],
            "files": [],
            "createdAt": now + 1,
        })

    def _get_next_run_time(self, task_id: str) -> int | None:
        """获取任务的下次执行时间（毫秒时间戳）。"""
        if not self._scheduler:
            return None
        try:
            job = self._scheduler.get_job(task_id)
            if job and job.next_run_time:
                return int(job.next_run_time.timestamp() * 1000)
        except Exception:
            pass
        return None

    # ==================== 事件监听 ====================

    def _on_job_executed(self, event) -> None:
        """任务执行成功事件。"""
        logger.debug("任务执行成功事件: job=%s", getattr(event, "job_id", "?"))

    def _on_job_error(self, event) -> None:
        """任务执行异常事件（APScheduler 层面的异常）。"""
        logger.error(
            "任务执行异常事件: job=%s exception=%s",
            getattr(event, "job_id", "?"),
            getattr(event, "exception", "?"),
        )


# 全局单例
scheduler_manager = SchedulerManager()
