"""旧版 RAG 检索-生成链模块。

组合查询扩写、多查询检索、提示模板和大模型，构建完整的问答链。
新版通用对话使用 rag/chat_chain.py，此模块保留供 /ask 接口兼容。
"""

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from server.config import RAGConfig
from server.llm import get_chat_model
from server.retrieval import expand_and_retrieve


_SYSTEM_PROMPT = """你是一个专业的智能文档问答助手。你的任务是基于检索到的参考上下文，准确、详尽地回答用户问题。

## 回答原则

1. **忠实于上下文**：所有回答必须基于参考上下文中的内容，不得编造、猜测或补充上下文中没有的信息。
2. **标注来源**：回答时在关键信息后用【章节名】标注信息来源，方便用户追溯原文。
3. **结构化输出**：对于复杂问题，使用分点/分段的方式组织回答，使内容清晰易读。
4. **信息不足时诚实说明**：如果上下文中没有足够的信息来完整回答问题，请明确指出"根据已知信息，无法完整回答该问题"，并说明缺少哪方面的信息。
5. **矛盾信息处理**：如果上下文中有相互矛盾的信息，请同时呈现不同说法，并标注各自来源。

## 回答格式

- 直接回答问题，不要重复问题本身
- 对于人物、事件、概念等问题，先给出核心结论，再补充细节
- 对于时间线/剧情相关问题，按时间顺序组织
- 回答语言与用户提问语言保持一致

## 参考上下文

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

    from server.knowledge_base import get_knowledge_base

    kb = get_knowledge_base(kb_id, config)
    return kb.collection_name if kb else "default"
