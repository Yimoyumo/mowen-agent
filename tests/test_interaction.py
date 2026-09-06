"""审批 scope 缓存测试（修复 #3）。

测试内容：
- normalize_file_pattern 生成 `op:绝对路径` pattern（文件操作不再只对 run 生效）
- 文件 op 批准 scope=session 后，第二次同路径命中缓存不弹卡（check_scope_cache 直接放行）
"""

import asyncio

import pytest

from server.agent import interaction
from server.agent.tools import _scope_key


class TestNormalizeFilePattern:
    """文件操作 pattern 归一化。"""

    def test_relative_path(self, tmp_path):
        key = interaction.normalize_file_pattern("write", "data.txt", tmp_path)
        assert key.startswith("write:")
        assert "data.txt" in key

    def test_absolute_path(self):
        key = interaction.normalize_file_pattern("read", "/workspace/a.txt", None)
        assert key == "read:/workspace/a.txt"

    def test_op_embedding(self):
        key = interaction.normalize_file_pattern("export", "x.csv", None)
        assert key.startswith("export:")


class TestScopeKeyHelper:
    """tools._scope_key 的 kind 路由。"""

    def test_file_uses_normalize_file(self, tmp_path):
        key = _scope_key("file", "write", "data.txt", tmp_path)
        assert key.startswith("write:")

    def test_run_uses_command_pattern(self):
        key = _scope_key("run", None, "pip install flask", None)
        assert key == "pip install *"


@pytest.mark.asyncio
async def test_file_scope_session_skip_second():
    """文件 op 批准 scope=session 后，同路径第二次命中缓存不再弹卡。"""
    interaction.set_ui_enabled(True)
    q: asyncio.Queue = asyncio.Queue()
    interaction.set_event_queue(q)
    try:
        # 第一次：文件 op 请求，批准 scope=session
        task = asyncio.ensure_future(
            interaction.request(
                "approval",
                {"command": "data.txt", "scope_key": "write:/abs/data.txt"},
                "s1",
                5,
            )
        )
        await asyncio.sleep(0.05)
        kind, ev = await q.get()
        assert ev["type"] == "interaction_request"
        assert interaction.answer(ev["request_id"], approved=True, scope="session") is True
        res = await task
        assert res["status"] == "answered"

        # 第二次：同文件路径应命中缓存
        assert interaction.check_scope_cache("s1", "write:/abs/data.txt") is True
        # 不同路径/不同 op 不命中
        assert interaction.check_scope_cache("s1", "write:/abs/other.txt") is False
        assert interaction.check_scope_cache("s1", "read:/abs/data.txt") is False
    finally:
        interaction.set_ui_enabled(True)
        interaction.set_event_queue(None)
