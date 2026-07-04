"""通用对话链模块。

支持多轮上下文对话，RAG 作为可选增强功能。

用法：
    # 纯对话
    chain = get_chat_chain()
    result = await chain.ainvoke({"messages": messages})

    # RAG 增强对话
    chain = get_chat_chain(kb_id="xxx")
    result = await chain.ainvoke({"messages": messages})
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from rag.config import RAGConfig
from rag.llm import get_chat_model
from rag.retriever import expand_and_retrieve
from rag.chain import _resolve_collection_name


_SYSTEM_PROMPT = """你是「墨问」，一个智能 AI 助手。你可以帮助用户回答问题、分析文档、进行创意写作等。

## 对话原则

1. **清晰准确**：回答应清晰、准确、有条理，避免模糊和歧义。
2. **上下文连贯**：结合对话历史，保持回答的连贯性和一致性。
3. **诚实透明**：不确定时坦诚说明，不编造信息。
4. **结构化输出**：对于复杂问题，使用分点/分段方式组织回答。
5. **语言一致**：回答语言与用户提问语言保持一致。
"""

_RAG_SYSTEM_PROMPT = """你是「墨问」，一个智能 AI 助手。你可以帮助用户回答问题、分析文档、进行创意写作等。

## 对话原则

1. **清晰准确**：回答应清晰、准确、有条理，避免模糊和歧义。
2. **上下文连贯**：结合对话历史，保持回答的连贯性和一致性。
3. **诚实透明**：不确定时坦诚说明，不编造信息。
4. **结构化输出**：对于复杂问题，使用分点/分段方式组织回答。
5. **语言一致**：回答语言与用户提问语言保持一致。

## 知识库增强

当提供了参考上下文时，请遵循：
- 优先基于参考上下文回答，在关键信息后用【来源】标注出处
- 参考上下文与对话历史冲突时，以参考上下文为准
- 参考上下文不足以回答时，可结合自身知识补充，但需说明哪些来自上下文、哪些来自模型自身知识
- 用户明确要求"仅基于文档"时，严格只使用参考上下文

## 参考上下文

{context}
"""


def _build_messages(raw_messages: list[dict], system_prompt: str, context_text: str = "") -> list:
    """将前端消息列表转为 LangChain 消息对象列表。

    Args:
        raw_messages: [{"role": "user"/"assistant", "content": "..."}]
        system_prompt: 系统提示词
        context_text: RAG 检索到的上下文文本（为空则不加上下文段）
    """
    prompt = context_text.format(context=context_text) if context_text else system_prompt
    messages = [SystemMessage(content=prompt)]

    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))

    return messages


async def chat_stream(
    messages: list[dict],
    kb_id: str | None = None,
    config: RAGConfig | None = None,
):
    """流式执行通用对话（可选 RAG 增强）。

    Args:
        messages: 对话历史 [{"role": "user"/"assistant", "content": "..."}]
        kb_id: 知识库 ID，提供时启用 RAG 检索增强
        config: RAG 配置

    Yields:
        字典序列：
        - {"type": "contexts", "contexts": ["..."]}  (仅 RAG 模式)
        - {"type": "token", "token": "..."}
        - {"type": "done"}
    """
    config = config or RAGConfig.from_json()
    llm = get_chat_model(config)

    context_texts: list[str] = []
    system_prompt = _SYSTEM_PROMPT
    context_template = ""

    if kb_id:
        # RAG 模式：检索相关文档
        collection_name = _resolve_collection_name(kb_id, config)
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if last_user_msg:
            docs = expand_and_retrieve(last_user_msg, collection_name, config)
            context_texts = [doc.page_content for doc in docs]

        system_prompt = _RAG_SYSTEM_PROMPT
        # 用模板替换，context_text 作为占位内容
        context_template = "{context}"

    lc_messages = _build_messages(messages, system_prompt, context_template)

    if context_texts:
        yield {"type": "contexts", "contexts": context_texts}

    async for token in llm.astream(lc_messages):
        content = _extract_token_content(token)
        if content:
            yield {"type": "token", "token": content}

    yield {"type": "done"}


def _extract_token_content(token) -> str:
    """从流式 Token 中提取文本内容。"""
    if isinstance(token, str):
        return token

    parts: list[str] = []
    if hasattr(token, "content") and token.content:
        parts.append(str(token.content))

    reasoning = getattr(token, "additional_kwargs", {}).get("reasoning_content", "")
    if reasoning:
        parts.append(str(reasoning))

    return "".join(parts)
