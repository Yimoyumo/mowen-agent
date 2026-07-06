"""提示词统一管理模块。

所有 LLM 提示词集中在此包管理，按场景拆分为子模块：
- agent.py:         Agent 系统提示词（分段组合）
- rag.py:           旧版 RAG 问答提示词
- query_expansion:  查询扩写提示词

设计原则：
1. 每个提示词用 PromptTemplate / ChatPromptTemplate 定义，支持变量注入
2. 大段提示词拆分为可组合的"段落"（PromptSection），按需拼接
3. 提示词内容用 Markdown 文本，便于阅读和维护
4. 所有提示词从此处统一导出，业务模块不再硬编码提示词

用法：
    from server.prompts import get_agent_system_prompt
    from server.prompts import RAG_CHAT_PROMPT
"""

from server.prompts.agent import (
    get_agent_system_prompt,
    get_time_section,
    get_skills_section,
    get_uploaded_files_section,
    get_memory_section,
)
from server.prompts.rag import RAG_CHAT_PROMPT, RAG_SYSTEM_TEMPLATE
from server.prompts.query_expansion import QUERY_EXPANSION_PROMPT, EXPANSION_SYSTEM_MSG

__all__ = [
    # Agent
    "get_agent_system_prompt",
    "get_time_section",
    "get_skills_section",
    "get_uploaded_files_section",
    "get_memory_section",
    # RAG
    "RAG_CHAT_PROMPT",
    "RAG_SYSTEM_TEMPLATE",
    # Query Expansion
    "QUERY_EXPANSION_PROMPT",
    "EXPANSION_SYSTEM_MSG",
]
