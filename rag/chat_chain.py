"""通用对话链模块。

支持多轮上下文对话，RAG 作为可选增强功能。

核心函数：chat_stream()
- 无 kb_id：纯对话模式，使用通用系统提示词
- 有 kb_id：RAG 模式，先检索相关文档，再注入提示词生成回答

用法：
    # 纯对话
    async for chunk in chat_stream(messages):
        ...

    # RAG 增强对话
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""
import asyncio
import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from rag.config import RAGConfig
from rag.llm import get_chat_model
from rag.retriever import expand_and_retrieve
from rag.chain import _resolve_collection_name


_SYSTEM_PROMPT = """你是「墨问」，一个智能 AI 助手。

## 你的身份

你是一个通用型 AI 对话助手，擅长日常聊天、知识问答、创意写作、代码编写、学习辅导等任务。你没有特定的知识库限制，可以运用自身所学的全部知识来帮助用户。

## 对话风格

- **亲切自然**：像朋友一样交流，语气友善但不啰嗦
- **简洁有力**：直奔主题，避免冗长的铺垫和重复
- **主动引导**：在回答后可以适当追问或提供建议，推动对话深入
- **灵活应变**：根据用户的问题难度和语气，调整回答的深度和风格

## 回答规范

1. 日常闲聊用口语化风格，技术问题用专业但易懂的语言
2. 复杂问题分点阐述，简单问题直接回答
3. 不确定的信息要诚实说明，不编造事实
4. 代码和公式使用 Markdown 格式输出
5. 回答语言与用户提问语言保持一致
"""


_RAG_SYSTEM_PROMPT = """你是「墨问」，一个专业的知识库问答助手。

## 你的身份

你当前处于**知识库增强模式**。用户已选择了特定的知识库，你的核心任务是基于检索到的参考上下文回答问题。你同时具备通用知识，但在此模式下应优先使用知识库中的内容。

## 回答原则

1. **忠于文档**：回答必须以参考上下文为主要依据，不得编造文档中不存在的信息。
2. **标注来源**：引用文档内容时，在关键信息后用【来源】标注出处，方便用户追溯。
3. **区分来源**：
   - 来自参考上下文的信息直接陈述
   - 参考上下文不足以完整回答时，可以补充自身知识，但必须明确说明"以下为模型补充，非文档内容"
4. **信息冲突**：当对话历史与参考上下文矛盾时，以参考上下文为准。
5. **诚实告知**：如果参考上下文中完全没有相关信息，直接告知"知识库中未找到相关内容"，不要强行回答。
6. **结构化输出**：对于复杂问题，使用分点/分段组织回答；对于简单事实查询，直接给出答案。

## 参考上下文

{context}
"""


# 按知识库类型定制的附加提示词
_KB_TYPE_PROMPTS: dict[str, str] = {
    "novel": """## 知识库类型：小说

当前知识库为**小说类**文档，可能包含正文、章节、人物描写、剧情等内容。回答时请注意：
- 涉及人物关系时，梳理清晰角色之间的关系链
- 涉及剧情时，按时间线或事件因果顺序组织
- 涉及设定/世界观时，区分原文设定与推测
- 引用原文对话或描写时，保持原文风格，用引号标注""",

    "tech": """## 知识库类型：技术文档

当前知识库为**技术文档类**，可能包含 API 文档、教程、规格说明等。回答时请注意：
- 代码、配置、命令行使用 Markdown 代码块输出，并标注语言
- 涉及 API 时，注明参数、返回值、异常等关键信息
- 涉及操作步骤时，按步骤编号，确保可复现
- 区分"文档明确说明"与"最佳实践建议"，后者需标注为补充""",

    "project": """## 知识库类型：项目文档

当前知识库为**项目文档类**，可能包含需求文档、设计文档、会议纪要等。回答时请注意：
- 涉及需求时，引用原始需求描述并标注来源
- 涉及设计决策时，说明背景和理由
- 涉及项目状态时，基于文档中的时间点回答，注意时效性
- 跨文档关联信息时，标注各信息来源""",

    "general": """## 知识库类型：通用文档

当前知识库为**通用文档类**，内容类型不限。回答时请注意：
- 先判断文档内容的主题和类型，再选择合适的回答方式
- 对于事实性内容，直接引用原文
- 对于观点性内容，标注为"文档中提到"
- 保持灵活的回答风格，适应不同类型的文档内容""",
}


def _get_rag_prompt(kb_type: str) -> str:
    """根据知识库类型获取 RAG 系统提示词。

    Args:
        kb_type: 知识库类型（novel/tech/project/general）
    """
    type_prompt = _KB_TYPE_PROMPTS.get(kb_type, _KB_TYPE_PROMPTS["general"])
    return _RAG_SYSTEM_PROMPT + "\n" + type_prompt


def _build_messages(raw_messages: list[dict], system_prompt: str, context_text: str = "") -> list:
    """将前端消息列表转为 LangChain 消息对象列表。

    Args:
        raw_messages: [{"role": "user"/"assistant", "content": "..."}]
        system_prompt: 系统提示词（RAG 模式下包含 {context} 占位符）
        context_text: RAG 检索到的上下文文本（为空则不替换占位符）
    """
    if "{context}" in system_prompt and context_text:
        prompt = system_prompt.replace("{context}", context_text)
    else:
        prompt = system_prompt
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
    stream: bool = True,
    show_reasoning: bool = False,
):
    """执行通用对话（可选 RAG 增强），流式或非流式输出。

    Args:
        messages: 对话历史 [{"role": "user"/"assistant", "content": "..."}]
        kb_id: 知识库 ID，提供时启用 RAG 检索增强
        config: RAG 配置
        stream: True 时逐 token 输出，False 时一次性返回
        show_reasoning: True 时额外返回模型推理过程

    Yields:
        字典序列：
        - {"type": "contexts", "contexts": ["..."]}  (仅 RAG 模式)
        - {"type": "reasoning", "token": "..."}       (仅 show_reasoning=True)
        - {"type": "token", "token": "..."}
        - {"type": "done"}
    """
    config = config or RAGConfig.from_json()
    llm = get_chat_model(config)

    context_texts: list[str] = []
    system_prompt = _SYSTEM_PROMPT
    context_template = ""

    if kb_id:
        # RAG 模式：检索相关文档并注入提示词
        from rag.knowledge_base import get_knowledge_base

        collection_name = _resolve_collection_name(kb_id, config)

        # 根据知识库类型选择对应提示词（小说/技术/项目/通用）
        kb = get_knowledge_base(kb_id, config)
        kb_type = kb.kb_type if kb else "general"
        system_prompt = _get_rag_prompt(kb_type)

        # 取最后一条用户消息作为检索查询
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        # 执行查询扩写 + 多查询检索
        if last_user_msg:
            docs = expand_and_retrieve(last_user_msg, collection_name, config)
            context_texts = [doc.page_content for doc in docs]

    # 将检索到的上下文拼入系统提示词的 {context} 占位符
    context_text = "\n\n---\n\n".join(context_texts) if context_texts else "（未检索到相关上下文）"
    lc_messages = _build_messages(messages, system_prompt, context_text)

    # 先返回检索到的上下文（供前端展示"参考上下文"按钮）
    if context_texts:
        yield {"type": "contexts", "contexts": context_texts}

    if stream:
        # 流式模式：逐 token 输出
        async for token in llm.astream(lc_messages):
            content, reasoning = _extract_token_content(token, show_reasoning)
            if reasoning:
                yield {"type": "reasoning", "token": reasoning}
            if content:
                yield {"type": "token", "token": content}
            # 让出控制权，确保 StreamingResponse 立即推送
            await asyncio.sleep(0)
    else:
        # 非流式模式：一次性返回完整回答
        result = await llm.ainvoke(lc_messages)
        content, reasoning = _extract_token_content(result, show_reasoning)
        if reasoning:
            yield {"type": "reasoning", "token": reasoning}
        if content:
            yield {"type": "token", "token": content}

    yield {"type": "done"}


def _extract_token_content(token, show_reasoning: bool = False) -> tuple[str, str]:
    """从流式 Token 中提取文本内容。

    返回 (content, reasoning) 元组：
    - content: 正式回答内容
    - reasoning: 推理过程内容（仅 show_reasoning=True 时提取）

    DeepSeek reasoner 等模型会把思考过程放在 additional_kwargs['reasoning_content'] 中。
    """
    if isinstance(token, str):
        return token, ""

    content = ""
    if hasattr(token, "content") and token.content:
        content = str(token.content)

    reasoning = ""
    if show_reasoning:
        reasoning = str(getattr(token, "additional_kwargs", {}).get("reasoning_content", ""))

    return content, reasoning
