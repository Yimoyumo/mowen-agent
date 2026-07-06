"""文件清理模块。

定期清理 uploads/ 和 downloads/ 目录中的过期文件，防止磁盘耗尽。

清理策略：
- uploads/：用户上传的文件，超过 1 小时未访问则删除（对话已结束，不再需要）
- downloads/：沙盒导出的文件，超过 24 小时则删除（用户已下载或不再需要）

触发方式：
- 应用启动时自动执行一次（清理上次运行遗留的文件）
- 之后每隔 1 小时自动执行一次（后台定时任务）

用法：
    from app.cleanup import start_cleanup_task, stop_cleanup_task

    # 应用启动时
    start_cleanup_task()

    # 应用关闭时
    stop_cleanup_task()
"""

import asyncio
import shutil
import time
from pathlib import Path

from server.logging_config import get_logger

logger = get_logger(__name__)

# 清理间隔（秒）
_CLEANUP_INTERVAL = 3600  # 1 小时

# 文件过期时间（秒）
_UPLOADS_MAX_AGE = 3600      # uploads/ 中文件最多保留 1 小时
_DOWNLOADS_MAX_AGE = 86400   # downloads/ 中文件最多保留 24 小时

# 清理的目录
_UPLOADS_DIR = Path("uploads")
_DOWNLOADS_DIR = Path("downloads")


def _cleanup_dir(directory: Path, max_age: int) -> int:
    """清理指定目录中过期的子目录/文件。

    按目录的修改时间判断是否过期。

    Args:
        directory: 要清理的目录
        max_age: 最大保留时间（秒）

    Returns:
        清理掉的条目数量
    """
    if not directory.exists():
        return 0

    now = time.time()
    removed = 0

    for entry in directory.iterdir():
        # 按修改时间判断
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue

        if now - mtime > max_age:
            try:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
            except Exception as exc:
                logger.warning("清理失败: %s | %s", entry, exc)

    return removed


async def _cleanup_loop():
    """后台清理循环，定期执行清理。"""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        run_cleanup()


def run_cleanup():
    """执行一次清理。"""
    u = _cleanup_dir(_UPLOADS_DIR, _UPLOADS_MAX_AGE)
    d = _cleanup_dir(_DOWNLOADS_DIR, _DOWNLOADS_MAX_AGE)
    if u or d:
        logger.info("文件清理完成 | uploads=%d downloads=%d", u, d)


# 后台任务句柄
_cleanup_task: asyncio.Task | None = None


def start_cleanup_task():
    """启动后台清理任务。

    立即执行一次清理（清理上次运行遗留的文件），
    然后每隔 _CLEANUP_INTERVAL 秒自动清理一次。
    """
    global _cleanup_task

    # 立即清理一次
    run_cleanup()

    # 启动后台定时任务
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(
            "文件清理任务已启动 | 间隔=%ds uploads_max=%ds downloads_max=%ds",
            _CLEANUP_INTERVAL, _UPLOADS_MAX_AGE, _DOWNLOADS_MAX_AGE,
        )


def stop_cleanup_task():
    """停止后台清理任务。"""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
        logger.info("文件清理任务已停止")
