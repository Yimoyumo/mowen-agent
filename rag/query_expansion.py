"""查询扩写模块。

使用 LLM 将用户问题扩展为多个语义相关的查询，提升召回率。
"""

from langchain_core.messages import SystemMessage, HumanMessage

from rag.config import RAGConfig
from rag.llm import get_chat_model


_EXPANSION_PROMPT = """你是一个查询扩写助手。
请根据用户的问题，生成 2 个语义相关但表达方式不同的查询。
这些查询将用于从向量数据库中检索相关文档。

要求：
- 保持原问题的核心意图
- 使用不同的关键词和句式
- 每个查询单独一行
- 不要输出编号、解释或多余内容

用户问题：{question}

相关查询："""


def expand_query(question: str, config: RAGConfig | None = None) -> list[str]:
    """将用户问题扩写为多个查询。

    Args:
        question: 原始用户问题。
        config: RAG 配置。

    Returns:
        扩写后的查询列表，包含原始问题。
    """
    config = config or RAGConfig.from_json()
    llm = get_chat_model(config)

    messages = [
        SystemMessage(content="你擅长生成语义检索查询。"),
        HumanMessage(content=_EXPANSION_PROMPT.format(question=question)),
    ]

    response = llm.invoke(messages)
    expanded = [line.strip("-• \t") for line in response.content.strip().split("\n") if line.strip()]

    # 把原始问题也加入列表，确保不丢失原意
    if question not in expanded:
        expanded.insert(0, question)

    return expanded
