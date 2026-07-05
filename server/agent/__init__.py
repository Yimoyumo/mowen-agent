"""Agent 模块。

基于 LangGraph 的 ReAct Agent，LLM 自主决定调用工具或直接回答。

核心 API：
- chat_stream: Agent 对话流式接口，完全兼容旧版 chat_chain.chat_stream()
- get_agent_tools: 获取 Agent 工具列表
- set_agent_context: 设置工具运行时上下文
"""

from server.agent.graph import chat_stream, _build_graph
from server.agent.tools import get_agent_tools, set_agent_context

__all__ = ["chat_stream", "get_agent_tools", "set_agent_context"]
