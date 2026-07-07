"""Agent 对话模块。

基于 LangGraph 构建 ReAct 风格的 Agent 对话循环。
LLM 自主决定调用工具或直接回答，支持流式输出。

核心函数：chat_stream() — 完全兼容旧版 chat_chain.chat_stream() 的接口。

用法：
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from server.config import RAGConfig
from server.llm import get_chat_model
from server.agent.tools import get_agent_tools, set_agent_context
from server.logging_config import get_logger

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
from server.user_settings import user_settings
from server.prompts import get_agent_system_prompt


# ==================== 构建图 ====================

def _build_graph(extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = "", memory_prompt: str = "", persona_prompt: str = "", profile_prompt: str = ""):
    """构建 LangGraph ReAct Agent。

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

    return create_react_agent(llm, all_tools, prompt=prompt)


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
    """Agent 对话（流式 / 非流式输出），完全兼容旧版 chat_chain.chat_stream()。

    Args:
        uploaded_files: [{token, filename}] 用户上传的文件，Agent 自动导入沙盒
        session_id: 会话 ID，用于沙盒跨消息持久化。同一 session_id 的消息共享同一沙盒。

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

    logger.info("对话开始 | messages=%d kb_id=%s stream=%s provider=%s model=%s session=%s",
                len(messages), kb_id, stream, config.chat_provider, config.chat_model, session_id)

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
        for f in uploaded_files:
            host_path = f"uploads/{f['token']}/{f['filename']}"
            dest = sb.import_file(host_path)
            if dest:
                parts.append(f"- {f['filename']} → {dest}")
            else:
                parts.append(f"- {f['filename']} → 导入失败")
        if parts:
            uploaded_info = "(系统提示：用户本次上传了以下文件，已导入沙盒，可直接处理。)\n" + "\n".join(parts)

    try:
        # 构建 LangChain 消息列表（根据模型上下文窗口自动截断）
        lc_messages, input_tokens = _build_messages(messages, config)

        if not stream:
            graph = _build_graph(extra_tools=mcp_tools, config=config, uploaded_info=uploaded_info, memory_prompt=memory_prompt, persona_prompt=persona_prompt, profile_prompt=profile_prompt)
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config={"recursion_limit": 50},
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
        async for event in _stream_agent(lc_messages, show_reasoning, mcp_tools, config, uploaded_info, memory_prompt, persona_prompt, profile_prompt):
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

def _build_messages(raw_messages: list[dict], config: RAGConfig | None = None) -> tuple[list, int]:
    """将前端消息列表转为 LangChain 消息对象。

    系统提示词由 create_react_agent 的 prompt 参数注入（在 _build_graph 中），
    这里只需构建对话历史消息。

    如果配置了 max_context_tokens 或模型有上下文窗口限制，
    从最旧的消息开始丢弃，确保总 token 数不超过限制。

    Returns:
        (messages, total_tokens) — 消息列表和总 token 估算值
    """
    # 先转为 LangChain 消息
    all_messages = []
    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            all_messages.append(AIMessage(content=content))
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


async def _stream_agent(messages: list, show_reasoning: bool, extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = "", memory_prompt: str = "", persona_prompt: str = "", profile_prompt: str = ""):
    """流式执行 Agent，逐 token / 工具事件输出。"""
    graph = _build_graph(extra_tools=extra_tools, config=config, uploaded_info=uploaded_info, memory_prompt=memory_prompt, persona_prompt=persona_prompt, profile_prompt=profile_prompt)

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": 50},
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

    except Exception as exc:
        logger.error("Agent 执行出错: %s", exc, exc_info=True)
        yield {"type": "token", "token": f"\n\n（Agent 出错: {exc}）"}

    yield {"type": "done"}
