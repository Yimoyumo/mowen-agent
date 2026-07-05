"""墨问 - AI 助手 API 入口。

用法：
    uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000

实际应用定义在 app/ 包中，此文件仅做转发。
"""

from app.main import app  # noqa: F401
