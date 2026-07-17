"""Agent 对话模块。

基于 LangGraph 构建 ReAct 风格的 Agent 对话循环。
LLM 自主决定调用工具或直接回答，支持流式输出。

核心函数：chat_stream() — 完全兼容旧版 chat_chain.chat_stream() 的接口。

用法：
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""

import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import create_agent

from server.core.config import RAGConfig
from server.llm.factory import get_chat_model
from server.agent.tools import get_agent_tools, set_agent_context
from server.agent.checkpointer import get_checkpointer
from server.core.logging_config import get_logger

logger = get_logger(__name__)


import math

def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文约 1.5 字/token，英文约 4 字符/token。"""
    if not text:
        return 0
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_count
    return max(1, math.ceil(chinese_count / 1.5 + other_chars / 4))

from server.agent.memory import memory_store
from server.core.user_settings import user_settings
from server.prompts import get_agent_system_prompt


# ==================== 构建图 ====================

async def _build_graph(extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = "", memory_prompt: str = "", persona_prompt: str = "", profile_prompt: str = ""):
    """构建 LangGraph ReAct Agent（带 Checkpointer 短期记忆）。

    Args:
        extra_tools: 额外工具（如 MCP 工具），合并到内置工具后传给 Agent
        config: RAG 配置（用于加载技能等动态段落）
        uploaded_info: 上传文件信息文本，注入系统提示词
        memory_prompt: 记忆提示词文本，注入系统提示词
        persona_prompt: 人格设定文本，注入系统提示词开头
        profile_prompt: 用户画像文本，注入系统提示词
    """
    cfg = config or RAGConfig.from_settings()
    llm = get_chat_model(cfg)

    # 合并内置工具和外部工具
    all_tools = get_agent_tools()
    if extra_tools:
        all_tools = all_tools + extra_tools

    # 从 server.prompts 组装完整系统提示词（含人格 + 技能 + 时间 + 记忆 + 画像 + 上传文件）
    prompt = get_agent_system_prompt(
        cfg,
        uploaded_info=uploaded_info,
        memory_prompt=memory_prompt,
        persona_prompt=persona_prompt,
        profile_prompt=profile_prompt,
    )

    # 获取 Checkpointer（SQLite 持久化，自动保存/恢复消息历史含工具结果）
    checkpointer = await get_checkpointer()

    return create_agent(llm, all_tools, system_prompt=prompt, checkpointer=checkpointer)


# ==================== 统一对外接口 ====================

async def chat_stream(
    messages: list[dict],
    kb_id: str | None = None,
    config: RAGConfig | None = None,
    stream: bool = True,
    show_reasoning: bool = False,
    uploaded_files: list[dict] | None = None,
    session_id: str | None = None,
):
    """Agent 对话（流式 / 非流式输出）。

    使用 LangGraph Checkpointer 实现短期记忆持久化：
    - 每次对话后自动保存完整状态（含 ToolMessage 工具结果）
    - 下次对话通过 thread_id 自动恢复历史
    - 工具调用结果跨请求保留，LLM 能看到之前的工具输出

    Args:
        uploaded_files: [{token, filename}] 用户上传的文件，Agent 自动导入沙盒
        session_id: 会话 ID，同时用作 Checkpointer thread_id 和沙盒标识。
                   同一 session_id 的消息共享历史和沙盒。

    Agent 自主决定：
    - 何时检索知识库
    - 何时联网搜索
    - 何时直接回答

    Yields:
        字典序列：
        - {"type": "tool_start", "tool": "search_web", "input": "..."}
        - {"type": "tool_end", "tool": "search_web", "output": "..."}
        - {"type": "reasoning", "token": "..."}       (仅 show_reasoning=True)
        - {"type": "token", "token": "..."}
        - {"type": "done"}
    """
    config = config or RAGConfig.from_settings()

    # 将 kb_id、config 和 session_id 注入工具上下文
    set_agent_context(kb_id, config, session_id)

    # 使用 session_id 作为 Checkpointer thread_id
    thread_id = session_id or "default"

    logger.info("对话开始 | messages=%d kb_id=%s stream=%s provider=%s model=%s thread=%s",
                len(messages), kb_id, stream, config.chat_provider, config.chat_model, thread_id)

    # 加载记忆，注入 system prompt
    memory_prompt = memory_store.get_prompt()
    if memory_prompt:
        logger.debug("记忆已注入: %d 字符", len(memory_prompt))

    # 加载人格设定和用户画像
    persona_prompt = user_settings.get_persona_prompt()
    profile_prompt = user_settings.get_profile_prompt()
    if persona_prompt:
        logger.debug("人格设定已注入: %d 字符", len(persona_prompt))
    if profile_prompt:
        logger.debug("用户画像已注入: %d 字符", len(profile_prompt))

    # 加载 MCP 工具
    from server.agent.mcp import load_mcp_tools
    mcp_tools = await load_mcp_tools(config.mcp_servers or {})

    # 沙盒：按 session_id 获取或创建（跨消息持久化）
    from server.agent.sandbox import get_or_create as get_or_create_sandbox
    sb = None
    if session_id:
        sb = get_or_create_sandbox(session_id)
        logger.debug("沙盒就绪: session=%s container=%s", session_id, sb.container_id)
    else:
        logger.debug("无 session_id，沙盒不可用")

    # 将用户上传的文件导入沙盒
    uploaded_info = ""
    if uploaded_files and sb:
        parts = []
        image_count = 0
        for f in uploaded_files:
            host_path = f"uploads/{f['token']}/{f['filename']}"
            # 图片不导入沙盒（视觉模型直接看图，沙盒不需要处理图片）
            suffix = Path(f["filename"]).suffix.lower() if f.get("filename") else ""
            if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
                image_count += 1
                continue
            dest = sb.import_file(host_path)
            if dest:
                parts.append(f"- {f['filename']} → {dest}")
            else:
                parts.append(f"- {f['filename']} → 导入失败")
        if parts:
            uploaded_info = "(系统提示：用户本次上传了以下文件，已导入沙盒，可直接处理。)\n" + "\n".join(parts)

        # 记录文件到沙盒管理器，沙盒重建时自动重新导入
        if uploaded_files:
            from server.agent.sandbox import track_session_files
            track_session_files(session_id, uploaded_files)

        if image_count > 0 and config and config.has_active_model_vision():
            hint = "（系统提示：用户上传了图片，图片内容已直接展示在你的视野中。请直接观察并回答图片相关问题，无需调用工具查看或处理图片。仅当用户明确要求编辑/转换图片时才使用沙盒工具。）"
            uploaded_info = (uploaded_info + "\n\n" + hint) if uploaded_info else hint

    try:
        # 构建 LangChain 消息列表（根据模型上下文窗口自动截断）
        lc_messages, input_tokens = _build_messages(messages, config, uploaded_files)

        # 构建 graph config（含 thread_id，Checkpointer 自动恢复历史）
        graph_config = {
            "recursion_limit": 100,
            "configurable": {"thread_id": thread_id},
        }

        if not stream:
            graph = await _build_graph(extra_tools=mcp_tools, config=config, uploaded_info=uploaded_info, memory_prompt=memory_prompt, persona_prompt=persona_prompt, profile_prompt=profile_prompt)
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config=graph_config,
            )
            final = result["messages"][-1]
            output_tokens = _estimate_tokens(str(final.content))
            ctx_window = config.get_active_model_context_window()
            yield {"type": "token", "token": str(final.content)}
            yield {"type": "done", "input_tokens": input_tokens, "output_tokens": output_tokens, "context_window": ctx_window}
            return

        # 流式模式：实时统计输出 token
        output_token_count = 0
        ctx_window = config.get_active_model_context_window()
        async for event in _stream_agent(lc_messages, show_reasoning, mcp_tools, config, uploaded_info, memory_prompt, persona_prompt, profile_prompt, thread_id=thread_id):
            if event.get("type") == "token":
                output_token_count += _estimate_tokens(event.get("token", ""))
                # 每个 token 事件附带实时统计
                yield {
                    "type": "token",
                    "token": event["token"],
                    "input_tokens": input_tokens,
                    "output_tokens": output_token_count,
                    "context_window": ctx_window,
                }
            elif event.get("type") == "reasoning":
                yield event
            elif event.get("type") == "done":
                yield {
                    "type": "done",
                    "input_tokens": input_tokens,
                    "output_tokens": output_token_count,
                    "context_window": ctx_window,
                }
                # 跳过后面的 schedule_extraction（在 finally 外面处理）
                break
            else:
                yield event
    finally:
        # 沙盒跨消息持久化：不在此销毁
        logger.info("对话结束")

    # 对话结束后：调度延迟记忆提取（90 秒内无新消息才执行）
    # 不阻塞 done 事件，提取在后台异步进行
    memory_store.schedule_extraction(messages)


# ==================== 内部实现 ====================

def _compress_and_encode_image(filepath: str, max_size: int = 1024, quality: int = 75) -> str | None:
    """压缩图片并返回 base64 编码。

    将图片缩小到 max_size px（最长边），转 JPEG 压缩，
    大幅减少 token 消耗。典型效果：2MB PNG → 80KB JPEG → ~20K tokens。

    Returns:
        base64 编码字符串，失败返回 None
    """
    import io
    import base64
    from PIL import Image

    try:
        img = Image.open(filepath)
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        raw = buf.getvalue()
        logger.debug("图片压缩: %s (%dx%d → %dx%d, %d bytes)",
                     filepath, w, h, img.width, img.height, len(raw))
        return base64.b64encode(raw).decode("utf-8")
    except Exception as e:
        logger.warning("图片压缩失败: %s (%s)", filepath, e)
        return None


def _build_messages(raw_messages: list[dict], config: RAGConfig | None = None, uploaded_files: list[dict] | None = None) -> tuple[list, int]:
    """将前端消息列表转为 LangChain 消息对象。

    多模态：有视觉能力 → 压缩后的图片 base64 嵌入；无视觉 → 注入"不识图"提示。
    Returns: (messages, total_tokens)
    """
    # 判断当前模型是否支持视觉
    has_vision = config.has_active_model_vision() if config else False

    # 提取本次上传的图片文件
    image_files = []
    if uploaded_files:
        for f in uploaded_files:
            filename = f.get("filename", "")
            suffix = Path(filename).suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
                image_files.append(f)

    # 构建“无法识图”提示（如果模型不支持视觉但用户上传了图片）
    no_vision_hint = ""
    if image_files and not has_vision:
        names = ", ".join(f["filename"] for f in image_files)
        no_vision_hint = f"\n\n（系统提示：用户上传了图片 [{names}]，但当前模型不支持视觉/识图。请在回复中告知用户当前模型无法识别图片，建议更换支持视觉的模型。）"

    # 先转为 LangChain 消息
    all_messages = []
    for i, msg in enumerate(raw_messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            all_messages.append(AIMessage(content=content))
        else:
            # 最后一条用户消息 + 模型支持视觉 + 有图片 → 构建多模态消息
            is_last_user = (i == len(raw_messages) - 1)
            if is_last_user and has_vision and image_files:
                # 构建多模态 content
                multimodal_content = []
                if content:
                    multimodal_content.append({"type": "text", "text": content})
                for f in image_files:
                    host_path = f"uploads/{f['token']}/{f['filename']}"
                    try:
                        b64 = _compress_and_encode_image(host_path)
                        if b64:
                            multimodal_content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            })
                    except Exception as e:
                        logger.warning("读取图片失败: %s (%s)", host_path, e)
                all_messages.append(HumanMessage(content=multimodal_content))
            elif is_last_user and no_vision_hint:
                all_messages.append(HumanMessage(content=content + no_vision_hint))
            else:
                all_messages.append(HumanMessage(content=content))

    # 计算截断上限
    limit = 0
    if config:
        # 用户手动设的 max_context_tokens（0 = 不限制）
        limit = config.max_context_tokens
        # 如果没设，自动用模型上下文窗口的 80%（留 20% 给输出）
        if limit <= 0:
            ctx_window = config.get_active_model_context_window()
            if ctx_window > 0:
                max_out = config.get_active_model_max_output()
                limit = ctx_window - max_out if max_out > 0 else int(ctx_window * 0.8)

    if limit <= 0 or not all_messages:
        total = sum(_estimate_tokens(str(m.content)) for m in all_messages)
        return all_messages, total

    # 从最新的消息往回累加，超出限制时丢弃最旧的
    total_tokens = 0
    kept = []
    for msg in reversed(all_messages):
        msg_tokens = _estimate_tokens(str(msg.content))
        if total_tokens + msg_tokens > limit and kept:
            # 加上这条就超了，且已有消息保留，丢弃更旧的
            break
        kept.append(msg)
        total_tokens += msg_tokens

    kept.reverse()

    if len(kept) < len(all_messages):
        logger.info("上下文截断: %d → %d 条消息 (约 %d tokens, 上限 %d)",
                    len(all_messages), len(kept), total_tokens, limit)

    return kept, total_tokens


async def _stream_agent(messages: list, show_reasoning: bool, extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = "", memory_prompt: str = "", persona_prompt: str = "", profile_prompt: str = "", thread_id: str = "default"):
    """流式执行 Agent，逐 token / 工具事件输出。

    Args:
        thread_id: Checkpointer thread_id，用于自动恢复/保存历史。
    """
    graph = await _build_graph(extra_tools=extra_tools, config=config, uploaded_info=uploaded_info, memory_prompt=memory_prompt, persona_prompt=persona_prompt, profile_prompt=profile_prompt)

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            config={
                "recursion_limit": 100,
                "configurable": {"thread_id": thread_id},
            },
        ):
            event_type = event.get("event", "")

            # -- LLM 流式输出的 token --
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                content = str(chunk.content) if hasattr(chunk, "content") and chunk.content else ""

                # 推理过程（DeepSeek reasoner）
                if show_reasoning:
                    reasoning = str(
                        getattr(chunk, "additional_kwargs", {}).get("reasoning_content", "")
                    )
                    if reasoning:
                        yield {"type": "reasoning", "token": reasoning}

                if content:
                    yield {"type": "token", "token": content}
                    await asyncio.sleep(0)

            # -- 工具调用开始 --
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", "")
                logger.info("工具调用开始: %s | input=%s", tool_name, str(tool_input)[:200])
                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "input": str(tool_input),
                }

            # -- 工具调用结束 --
            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                output = event.get("data", {}).get("output", "")

                # ToolMessage 的 output 可能是 ToolMessage 对象
                if hasattr(output, "content"):
                    output = str(output.content)

                logger.info("工具调用完成: %s | output_len=%d", tool_name, len(str(output)))
                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": str(output)[:500],  # 截断过长输出
                }

                # sandbox_export_file 返回了图片 markdown，注入到消息流中直接渲染
                if tool_name == "sandbox_export_file":
                    import re
                    img_re = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
                    for m in img_re.finditer(str(output)):
                        yield {"type": "token", "token": "\n\n" + m.group(0) + "\n\n"}
                        await asyncio.sleep(0)

    except Exception as exc:
        logger.error("Agent 执行出错: %s", exc, exc_info=True)
        yield {"type": "token", "token": f"\n\n（Agent 出错: {exc}）"}

    yield {"type": "done"}
