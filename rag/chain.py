"""RAG 检索-生成链模块。

组合查询扩写、多查询检索、提示模板和大模型，构建完整的问答链。
"""

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from rag.config import RAGConfig
from rag.llm import get_chat_model
from rag.retriever import expand_and_retrieve


_SYSTEM_PROMPT = """你是一个基于已知上下文回答问题的助手。
请严格根据以下参考上下文回答问题。如果上下文中没有相关信息，请明确说明"根据已知信息无法回答"。

参考上下文：
{context}
"""


def get_rag_chain(kb_id: str | None = None, config: RAGConfig | None = None):
    """构建带查询扩写的 RAG 检索生成链。

    Args:
        kb_id: 知识库 ID，为空时使用默认知识库。
        config: RAG 配置。

    Returns:
        调用 invoke({"input": question}) 后返回 {"input", "context", "answer"} 字典。
    """
    config = config or RAGConfig.from_json()
    llm = get_chat_model(config)
    collection_name = _resolve_collection_name(kb_id, config)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", "{input}"),
        ]
    )

    question_answer_chain = create_stuff_documents_chain(llm, prompt)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config)
        )
        | RunnablePassthrough.assign(answer=question_answer_chain)
    )


def get_rag_streaming_chain(kb_id: str | None = None, config: RAGConfig | None = None):
    """构建可流式输出的 RAG 链。

    与 get_rag_chain 类似，但 answer 字段直接绑定 LLM 的流式输出（异步迭代器）。
    """
    config = config or RAGConfig.from_json()
    llm = get_chat_model(config)
    collection_name = _resolve_collection_name(kb_id, config)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", "{input}"),
        ]
    )

    async def generate_answer(x: dict) -> object:
        formatted_messages = prompt.format_messages(context=x["context"], input=x["input"])
        return llm.astream(formatted_messages)

    return (
        RunnablePassthrough.assign(
            context=lambda x: expand_and_retrieve(x["input"], collection_name, config)
        )
        | RunnablePassthrough.assign(answer=generate_answer)
    )


def _resolve_collection_name(kb_id: str | None, config: RAGConfig | None = None) -> str:
    """将知识库 ID 解析为 Chroma collection 名称。"""
    if not kb_id:
        return "default"

    from rag.knowledge_base import get_knowledge_base

    kb = get_knowledge_base(kb_id, config)
    return kb.collection_name if kb else "default"
