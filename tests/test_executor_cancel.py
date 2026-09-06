"""HostExecutor cancel 测试（修复 #4）。

测试内容：
- 运行中的 long 命令被 cancel 后，ExecResult.cancelled=True、timed_out=False、exit_code=-1
- 已结束的命令 cancel 不误判为 cancelled
"""

import asyncio

import pytest

from server.agent.executor.host import HostExecutor


@pytest.mark.asyncio
async def test_cancel_sets_cancelled(tmp_path):
    ex = HostExecutor({"workspace_root": str(tmp_path / "host_ws")})
    task = asyncio.ensure_future(ex.run("s1", "sleep 100", timeout=120))
    await asyncio.sleep(0.3)

    st = ex.status()
    assert st["running"], "应有运行中的操作"
    op_id = st["running"][0]["op_id"]

    ok = await ex.cancel(op_id)
    assert ok is True

    result = await task
    assert result.cancelled is True
    assert result.timed_out is False
    assert result.exit_code == -1
    assert "已被取消" in result.output


@pytest.mark.asyncio
async def test_cancel_after_finished_not_cancelled(tmp_path):
    ex = HostExecutor({"workspace_root": str(tmp_path / "host_ws")})
    result = await ex.run("s1", "echo hi", timeout=10)
    assert result.cancelled is False
    # 对已结束的 op cancel：找不到运行中的 op
    ok = await ex.cancel(result.op_id)
    assert ok is False
