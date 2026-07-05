"""对话链模块（兼容层）。

所有对话逻辑已迁移到 rag/agent.py，此模块仅做重导出以保持向后兼容。

用法不变：
    from server.chat_chain import chat_stream
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""

from server.agent import chat_stream  # noqa: F401 — 兼容旧 import 路径
