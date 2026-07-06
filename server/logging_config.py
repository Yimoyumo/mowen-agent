"""日志模块。

提供统一的日志配置和 Logger 工厂，支持按模块名获取独立 Logger。
所有模块通过 get_logger(__name__) 获取 Logger，无需关心底层配置。

特性：
- 控制台彩色输出（开发环境）+ 文件轮转（生产环境）
- 按模块名隔离日志级别，可独立调试某个模块
- 配置驱动：通过 config.json 的 "logging" 字段调整级别/格式/文件
- 请求追踪：HTTP 中间件自动注入 request_id

用法：
    from server.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
    logger.debug("调试信息")  # 默认不输出，可通过配置开启

配置示例（config.json）：
    "logging": {
        "level": "INFO",
        "file": "logs/mowen.log",
        "max_bytes": 10485760,
        "backup_count": 5,
        "modules": {
            "server.agent": "DEBUG",
            "server.retrieval": "DEBUG"
        }
    }
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from server.config import RAGConfig


# ==================== 日志格式 ====================

class _ColorFormatter(logging.Formatter):
    """控制台彩色格式化器。

    为不同级别使用不同颜色，提升开发体验。
    """

    # ANSI 颜色码
    _COLORS = {
        logging.DEBUG: "\033[36m",     # 青色
        logging.INFO: "\033[32m",      # 绿色
        logging.WARNING: "\033[33m",   # 黄色
        logging.ERROR: "\033[31m",    # 红色
        logging.CRITICAL: "\033[35m",  # 紫色
    }
    _RESET = "\033[0m"

    # 格式：时间 | 级别 | 模块 | 消息
    _FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    _DATE_FORMAT = "%H:%M:%S"

    def __init__(self, use_color: bool = True):
        super().__init__(fmt=self._FORMAT, datefmt=self._DATE_FORMAT)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if not self._use_color:
            return super().format(record)

        color = self._COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname:<7}{self._RESET}"
        return super().format(record)


# 文件日志格式（无颜色，含完整时间）
_FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
_FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ==================== 配置加载 ====================

def _load_log_config() -> dict:
    """从 config.json 读取日志配置。

    返回结构：
        {
            "level": "INFO",
            "file": "logs/mowen.log",   # None 表示不写文件
            "max_bytes": 10485760,
            "backup_count": 5,
            "modules": {"server.agent": "DEBUG", ...}
        }
    """
    try:
        config = RAGConfig.from_json()
        raw = getattr(config, "logging", None) or {}
    except Exception:
        # 配置加载失败时使用默认值，绝不因日志初始化失败而崩溃
        return {}

    return {
        "level": raw.get("level", "INFO"),
        "file": raw.get("file", "logs/mowen.log"),
        "max_bytes": raw.get("max_bytes", 10 * 1024 * 1024),  # 10MB
        "backup_count": raw.get("backup_count", 5),
        "modules": raw.get("modules", {}),
    }


# ==================== 初始化 ====================

_initialized = False
"""标记是否已初始化，避免重复添加 handler。"""


def setup_logging() -> None:
    """初始化全局日志配置。

    幂等操作，多次调用安全。在应用启动时调用一次即可。

    - 设置根 Logger 级别
    - 添加控制台 handler（彩色）
    - 添加文件 handler（轮转）
    - 设置各模块独立级别
    """
    global _initialized
    if _initialized:
        return

    cfg = _load_log_config()
    root = logging.getLogger()

    # 全局级别
    root.setLevel(cfg["level"])

    # 清除已有 handler（防止 uvicorn --reload 重复添加）
    root.handlers.clear()

    # ---- 控制台 handler ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(cfg["level"])
    console_handler.setFormatter(_ColorFormatter(use_color=sys.stdout.isatty()))
    root.addHandler(console_handler)

    # ---- 文件 handler ----
    file_path = cfg.get("file")
    if file_path:
        log_dir = Path(file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=file_path,
            maxBytes=cfg["max_bytes"],
            backupCount=cfg["backup_count"],
            encoding="utf-8",
        )
        file_handler.setLevel(cfg["level"])
        file_handler.setFormatter(
            logging.Formatter(fmt=_FILE_FORMAT, datefmt=_FILE_DATE_FORMAT)
        )
        root.addHandler(file_handler)

    # ---- 模块级别 ----
    for module_name, level in cfg["modules"].items():
        logging.getLogger(module_name).setLevel(level)

    _initialized = True
    root.info("日志系统已初始化 | level=%s | file=%s", cfg["level"], file_path or "禁用")


# ==================== Logger 工厂 ====================

def get_logger(name: str) -> logging.Logger:
    """获取指定模块的 Logger。

    首次调用时自动初始化全局配置，无需手动调用 setup_logging()。

    Args:
        name: 模块名，通常传 __name__

    Returns:
        配置好的 Logger 实例
    """
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)


# ==================== 请求追踪上下文 ====================

import contextvars

# 当前请求 ID，由 HTTP 中间件设置
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """在日志中注入 request_id 字段。

    配合格式中的 %(request_id)s 使用，实现请求级别的日志追踪。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def set_request_id(request_id: str) -> None:
    """设置当前请求 ID（由 HTTP 中间件调用）。"""
    _request_id.set(request_id)


def get_request_id() -> str:
    """获取当前请求 ID。"""
    return _request_id.get()
