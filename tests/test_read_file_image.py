"""read_file 工具图片 / 二进制处理测试。

- 图片 + 视觉模型 → 返回多模态 content blocks（image_url data URL）
- 图片 + 非视觉模型 → 明确提示不支持视觉，不报"不存在"
- 其他二进制文件 → 明确提示"二进制文件"，不再误报"不存在"
- 缺失文件 → 保留"不存在"提示
"""

import io

from PIL import Image

from server.agent.executor import get_executor
from server.agent.tools import read_file, set_agent_context
from server.core.config import RAGConfig


def _make_config(tmp_path, active_model: str) -> RAGConfig:
    """host 执行器 + 临时工作区 + 跳过审批。"""
    return RAGConfig(
        active_model=active_model,
        executor_mode="host",
        executor_config={
            "workspace_root": str(tmp_path / "ws"),
            "approval_mode": "auto",
        },
    )


def _patch_overrides(monkeypatch, overrides: dict) -> None:
    """注入确定性的 model_context_overrides，不依赖开发者本机 user_settings.json。"""
    from server.core import user_settings as us
    monkeypatch.setattr(
        us.user_settings, "load", lambda: {"model_context_overrides": overrides}
    )


def _make_png_bytes(color=(200, 60, 60), size=(600, 400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


async def _invoke_read(path: str):
    """按生产路径调用工具（tool_call 输入 → ToolMessage 包装）。"""
    out = await read_file.ainvoke(
        {"type": "tool_call", "name": "read_file", "args": {"path": path}, "id": "t1"}
    )
    return out.content if hasattr(out, "content") else out


async def test_read_image_with_vision_model(tmp_path, monkeypatch):
    _patch_overrides(
        monkeypatch,
        {"openai/gpt-4o": {"context_window": 128000, "max_output": 16384, "has_vision": True}},
    )
    cfg = _make_config(tmp_path, "openai/gpt-4o")
    set_agent_context(None, cfg, "s-img-v")
    ex = get_executor(cfg)
    await ex.write_bytes("s-img-v", "chart.png", _make_png_bytes())

    content = await _invoke_read("chart.png")

    assert isinstance(content, list), f"视觉模型应返回 content blocks，实际: {type(content)}"
    texts = [b["text"] for b in content if b.get("type") == "text"]
    images = [b for b in content if b.get("type") == "image_url"]
    assert any("chart.png" in t for t in texts)
    assert len(images) == 1
    url = images[0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,"), "应压缩为 JPEG data URL"


async def test_read_image_with_non_vision_model(tmp_path, monkeypatch):
    _patch_overrides(monkeypatch, {})
    cfg = _make_config(tmp_path, "deepseek/deepseek-chat")
    set_agent_context(None, cfg, "s-img-nv")
    ex = get_executor(cfg)
    await ex.write_bytes("s-img-nv", "chart.png", _make_png_bytes())

    content = await _invoke_read("chart.png")

    assert isinstance(content, str)
    assert "不支持视觉" in content
    assert "不存在" not in content


async def test_read_corrupt_image_with_vision_model(tmp_path, monkeypatch):
    _patch_overrides(
        monkeypatch,
        {"openai/gpt-4o": {"context_window": 128000, "max_output": 16384, "has_vision": True}},
    )
    cfg = _make_config(tmp_path, "openai/gpt-4o")
    set_agent_context(None, cfg, "s-img-bad")
    ex = get_executor(cfg)
    await ex.write_bytes("s-img-bad", "bad.png", b"this is not an image")

    content = await _invoke_read("bad.png")

    assert isinstance(content, str)
    assert "解码失败" in content


async def test_read_binary_file_clear_message(tmp_path, monkeypatch):
    _patch_overrides(monkeypatch, {})
    cfg = _make_config(tmp_path, "openai/gpt-4o")
    set_agent_context(None, cfg, "s-bin")
    ex = get_executor(cfg)
    # zip 魔数 + NUL 字节：非图片的二进制文件
    await ex.write_bytes("s-bin", "data.bin", b"PK\x03\x04\x00\x00binary...")

    content = await _invoke_read("data.bin")

    assert isinstance(content, str)
    assert "二进制" in content
    assert "不存在" not in content


async def test_read_missing_file(tmp_path):
    set_agent_context(None, _make_config(tmp_path, "openai/gpt-4o"), "s-miss")

    content = await _invoke_read("nope.txt")

    assert "不存在" in content


async def test_read_missing_image(tmp_path):
    set_agent_context(None, _make_config(tmp_path, "openai/gpt-4o"), "s-miss-img")

    content = await _invoke_read("nope.png")

    assert "不存在" in content


async def test_read_text_file_still_works(tmp_path):
    cfg = _make_config(tmp_path, "openai/gpt-4o")
    set_agent_context(None, cfg, "s-txt")
    ex = get_executor(cfg)
    await ex.write_file("s-txt", "notes.txt", "hello 世界")

    content = await _invoke_read("notes.txt")

    assert content == "hello 世界"


# ==================== 用户上传图片的注入路径（graph._build_messages）====================

async def test_uploaded_image_injected_as_single_data_url(tmp_path, monkeypatch):
    """回归：上传图片注入多模态消息时，data URL 不能被套两层。

    曾出现过 prefix 重复（data:image/jpeg;base64,data:image/jpeg;base64,...）导致
    厂商返回 400 Invalid base64 data。read_file 那条路径是对的，此处单独守住上传路径。
    """
    from server.agent.graph import _build_messages

    _patch_overrides(
        monkeypatch,
        {"openai/gpt-4o": {"context_window": 128000, "max_output": 16384, "has_vision": True}},
    )
    cfg = _make_config(tmp_path, "openai/gpt-4o")

    # graph 里用的是相对路径 uploads/<token>/<文件名>，把工作目录切到 tmp_path
    monkeypatch.chdir(tmp_path)
    img_dir = tmp_path / "uploads" / "tok123"
    img_dir.mkdir(parents=True)
    (img_dir / "pic.png").write_bytes(_make_png_bytes())

    messages, _ = _build_messages(
        [{"role": "user", "content": "看看这张图"}],
        cfg,
        [{"token": "tok123", "filename": "pic.png"}],
    )

    blocks = messages[-1].content
    assert isinstance(blocks, list), f"视觉模型应构建多模态 content，实际: {blocks!r}"
    images = [b for b in blocks if b.get("type") == "image_url"]
    assert len(images) == 1

    url = images[0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,"), f"应为 JPEG data URL: {url[:60]!r}"
    assert url.count("data:") == 1, f"data URL 被重复拼接: {url[:80]!r}"
    # 去掉前缀后应是合法 base64
    import base64

    base64.b64decode(url.split(",", 1)[1], validate=True)


async def test_uploaded_image_with_non_vision_model_gets_hint(tmp_path, monkeypatch):
    """非视觉模型：不注入图片，改为提示"无法识别图片"。"""
    from server.agent.graph import _build_messages

    _patch_overrides(monkeypatch, {})
    cfg = _make_config(tmp_path, "deepseek/deepseek-chat")
    monkeypatch.chdir(tmp_path)

    messages, _ = _build_messages(
        [{"role": "user", "content": "看看这张图"}],
        cfg,
        [{"token": "tok123", "filename": "pic.png"}],
    )

    content = messages[-1].content
    assert isinstance(content, str)
    assert "不支持视觉" in content

