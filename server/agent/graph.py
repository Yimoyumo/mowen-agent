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
from server.prompts import get_agent_system_prompt

logger = get_logger(__name__)


# ==================== 构建图 ====================

def _build_graph(extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = ""):
    """构建 LangGraph ReAct Agent。

    Args:
        extra_tools: 额外工具（如 MCP 工具），合并到内置工具后传给 Agent
        config: RAG 配置（用于加载技能等动态段落）
        uploaded_info: 上传文件信息文本，注入系统提示词
    """
    cfg = config or RAGConfig.from_json()
    llm = get_chat_model(cfg)

    # 合并内置工具和外部工具
    all_tools = get_agent_tools()
    if extra_tools:
        all_tools = all_tools + extra_tools

    # 从 server.prompts 组装完整系统提示词（含技能 + 时间 + 上传文件）
    prompt = get_agent_system_prompt(cfg, uploaded_info=uploaded_info)

    return create_react_agent(llm, all_tools, prompt=prompt)


# ==================== 统一对外接口 ====================

async def chat_stream(
    messages: list[dict],
    kb_id: str | None = None,
    config: RAGConfig | None = None,
    stream: bool = True,
    show_reasoning: bool = False,
    uploaded_files: list[dict] | None = None,
):
    """Agent 对话（流式 / 非流式输出），完全兼容旧版 chat_chain.chat_stream()。

    Args:
        uploaded_files: [{token, filename}] 用户上传的文件，Agent 自动导入沙盒

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
    config = config or RAGConfig.from_json()

    # 将 kb_id 和 config 注入工具上下文
    set_agent_context(kb_id, config)

    logger.info("对话开始 | messages=%d kb_id=%s stream=%s", len(messages), kb_id, stream)

    # 加载 MCP 工具
    from server.agent.mcp import load_mcp_tools
    mcp_tools = await load_mcp_tools(config.mcp_servers or {})

    # 启动 Docker 沙盒（对话期间持久存在）
    from server.agent.sandbox import create as create_sandbox, destroy as destroy_sandbox
    create_sandbox()
    logger.debug("沙盒已启动")

    # 将用户上传的文件导入沙盒
    uploaded_info = ""
    if uploaded_files:
        from server.agent.sandbox import get as get_sandbox
        sb = get_sandbox()
        parts = []
        for f in uploaded_files:
            host_path = f"uploads/{f['token']}/{f['filename']}"
            dest = sb.import_file(host_path) if sb else None
            if dest:
                parts.append(f"- {f['filename']} → {dest}")
            else:
                parts.append(f"- {f['filename']} → 导入失败")
        if parts:
            uploaded_info = "(系统提示：用户本次上传了以下文件，已导入沙盒，可直接处理。)\n" + "\n".join(parts)

    try:
        # 构建 LangChain 消息列表
        lc_messages = _build_messages(messages)

        if not stream:
            graph = _build_graph(extra_tools=mcp_tools, config=config, uploaded_info=uploaded_info)
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config={"recursion_limit": 50},
            )
            final = result["messages"][-1]
            yield {"type": "token", "token": str(final.content)}
            yield {"type": "done"}
            return

        async for event in _stream_agent(lc_messages, show_reasoning, mcp_tools, config, uploaded_info):
            yield event
    finally:
        destroy_sandbox()
        logger.debug("沙盒已销毁")
        logger.info("对话结束")


# ==================== 内部实现 ====================

def _build_messages(raw_messages: list[dict]) -> list:
    """将前端消息列表转为 LangChain 消息对象。

    系统提示词由 create_react_agent 的 prompt 参数注入（在 _build_graph 中），
    这里只需构建对话历史消息。
    """
    messages = []

    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))

    return messages


async def _stream_agent(messages: list, show_reasoning: bool, extra_tools: list = None, config: RAGConfig | None = None, uploaded_info: str = ""):
    """流式执行 Agent，逐 token / 工具事件输出。"""
    graph = _build_graph(extra_tools=extra_tools, config=config, uploaded_info=uploaded_info)

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
