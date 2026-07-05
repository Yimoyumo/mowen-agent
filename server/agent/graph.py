"""Agent 对话模块。

基于 LangGraph 构建 ReAct 风格的 Agent 对话循环。
LLM 自主决定调用工具或直接回答，支持流式输出。

核心函数：chat_stream() — 完全兼容旧版 chat_chain.chat_stream() 的接口。

用法：
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""

import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict

from server.config import RAGConfig
from server.llm import get_chat_model
from server.agent.tools import get_agent_tools, set_agent_context


# ==================== 系统提示词 ====================

_SYSTEM_PROMPT = """你是「墨问」，一个智能 AI Agent 助手。

## 你的能力

你有以下工具可用：
1. **search_knowledge_base** — 搜索用户上传的知识库（文档、小说、技术资料等）
2. **search_web** — 联网搜索最新信息（新闻、天气、实时数据等）

## 工具使用原则

- 用户问知识库相关内容 → 优先用 search_knowledge_base
- 用户问实时信息 → 用 search_web
- 简单闲聊、常识问答 → 直接回答，不调工具
- 一次工具调用能解决的不要分多次
- 工具返回结果后，基于结果给出完整回答

## 对话风格

- **亲切自然**：像朋友一样交流
- **简洁有力**：直奔主题，不啰嗦
- **诚实透明**：不确定的要说不知道，用了工具要自然提及信息来源
- 回答语言与用户提问语言保持一致
"""


# ==================== Agent 状态 ====================

class AgentState(TypedDict):
    """Agent 状态图的状态定义。"""
    messages: list  # 完整对话历史 (SystemMessage + HumanMessages + AIMessages + ToolMessages)


# ==================== 节点函数 ====================

def _call_model(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 决策节点：让模型决定是调用工具还是直接回答。

    注意：config 参数由 LangGraph 自动注入（包含 runnable config）。
    我们的 RAGConfig 通过 tools.set_agent_context 提前设置好了。
    """
    llm = get_chat_model(RAGConfig.from_json())

    # 绑定工具到 LLM
    tools = get_agent_tools()
    llm_with_tools = llm.bind_tools(tools)

    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# ==================== 条件判断 ====================

def _should_continue(state: AgentState) -> str:
    """判断 Agent 下一步：继续调工具 or 结束对话。"""
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"  # 调用工具
    return "end"  # 直接回答


# ==================== 构建图 ====================

def _build_graph():
    """构建 LangGraph Agent 状态图。"""
    workflow = StateGraph(AgentState)

    tools = get_agent_tools()
    tool_node = ToolNode(tools)

    workflow.add_node("agent", _call_model)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        _should_continue,
        {"continue": "tools", "end": END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# ==================== 统一对外接口 ====================

async def chat_stream(
    messages: list[dict],
    kb_id: str | None = None,
    config: RAGConfig | None = None,
    stream: bool = True,
    show_reasoning: bool = False,
):
    """Agent 对话（流式 / 非流式输出），完全兼容旧版 chat_chain.chat_stream()。

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

    # 将 kb_id 和 config 注入工具上下文，工具函数内部通过 contextvars 读取
    set_agent_context(kb_id, config)

    # 构建 LangChain 消息列表
    lc_messages = _build_messages(messages)

    if not stream:
        # 非流式：一次性返回
        graph = _build_graph()
        result = await graph.ainvoke({"messages": lc_messages})

        final = result["messages"][-1]
        yield {"type": "token", "token": str(final.content)}
        yield {"type": "done"}
        return

    # 流式模式：逐 token 输出
    async for event in _stream_agent(lc_messages, show_reasoning):
        yield event


# ==================== 内部实现 ====================

def _build_messages(raw_messages: list[dict]) -> list:
    """将前端消息列表转为 LangChain 消息对象。"""
    messages = [SystemMessage(content=_SYSTEM_PROMPT)]

    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))

    return messages


async def _stream_agent(messages: list, show_reasoning: bool):
    """流式执行 Agent，逐 token / 工具事件输出。"""
    graph = _build_graph()

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
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

                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": str(output)[:500],  # 截断过长输出
                }

    except Exception as exc:
        yield {"type": "token", "token": f"\n\n（Agent 出错: {exc}）"}

    yield {"type": "done"}
