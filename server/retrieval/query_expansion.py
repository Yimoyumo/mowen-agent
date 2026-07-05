"""查询扩写模块。

使用 LLM 将用户问题扩展为多个语义相关的查询，提升召回率。
"""

from langchain_core.messages import SystemMessage, HumanMessage

from server.config import RAGConfig
from server.llm import get_chat_model


_EXPANSION_PROMPT = """你是一个专业的查询扩写助手，用于优化向量数据库的检索效果。
请根据用户的问题，从不同角度生成 2 个语义相关但表达方式不同的检索查询。

## 扩写策略

- **关键词替换**：用同义词或相关概念替换原始关键词
- **视角转换**：从不同角度描述同一信息需求
- **实体补全**：补充问题中隐含的相关实体名称
- **句式变化**：使用陈述句、疑问句等不同句式

## 要求

- 保持原问题的核心意图不变
- 每个查询单独占一行
- 不要输出编号、解释或任何多余内容
- 查询应当是简洁的检索短语，而非完整长句

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
        SystemMessage(content="你是一个专业的语义检索查询扩写助手，擅长从多角度生成高质量的检索查询。"),
        HumanMessage(content=_EXPANSION_PROMPT.format(question=question)),
    ]

    response = llm.invoke(messages)
    expanded = [line.strip("-• \t") for line in response.content.strip().split("\n") if line.strip()]

    # 把原始问题也加入列表，确保不丢失原意
    if question not in expanded:
        expanded.insert(0, question)

    return expanded
