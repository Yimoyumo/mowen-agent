"""查询扩写模块。

使用 LLM 将用户问题扩展为多个语义相关的查询，提升召回率。

提示词统一管理在 server/prompts/query_expansion.py 中。
"""

from langchain_core.messages import SystemMessage, HumanMessage

from server.config import RAGConfig
from server.llm import get_chat_model
from server.prompts import QUERY_EXPANSION_PROMPT, EXPANSION_SYSTEM_MSG


def expand_query(question: str, config: RAGConfig | None = None) -> list[str]:
    """将用户问题扩写为多个查询。

    Args:
        question: 原始用户问题。
        config: RAG 配置。

    Returns:
        扩写后的查询列表，包含原始问题。
    """
    config = config or RAGConfig.from_settings()
    llm = get_chat_model(config)

    # 用 PromptTemplate 格式化用户提示词
    user_prompt = QUERY_EXPANSION_PROMPT.format(question=question)

    messages = [
        SystemMessage(content=EXPANSION_SYSTEM_MSG),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    expanded = [line.strip("-• \t") for line in response.content.strip().split("\n") if line.strip()]

    # 把原始问题也加入列表，确保不丢失原意
    if question not in expanded:
        expanded.insert(0, question)

    return expanded
