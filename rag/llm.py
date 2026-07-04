"""大语言模型模块。

支持多厂商 Chat 模型，通过配置切换。
"""

from langchain_community.chat_models import ChatZhipuAI
from langchain_deepseek import ChatDeepSeek

from rag.config import RAGConfig


def _build_kwargs(config: RAGConfig) -> dict:
    """根据配置构造通用的 LLM 调用参数。"""
    kwargs: dict = {
        "model": config.chat_model,
        "temperature": config.temperature,
        "timeout": config.timeout,
        "streaming": config.streaming,
    }
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    if config.top_p is not None:
        kwargs["top_p"] = config.top_p
    if config.frequency_penalty is not None:
        kwargs["frequency_penalty"] = config.frequency_penalty
    if config.presence_penalty is not None:
        kwargs["presence_penalty"] = config.presence_penalty
    # DeepSeek / OpenAI 风格推理深度控制
    if config.reasoning_effort is not None:
        kwargs["reasoning_effort"] = config.reasoning_effort
    return kwargs


def get_chat_model(config: RAGConfig | None = None):
    """根据配置获取聊天模型实例。"""
    config = config or RAGConfig.from_json()
    kwargs = _build_kwargs(config)

    if config.chat_provider == "deepseek":
        if not config.deepseek_api_key:
            raise ValueError("使用 DeepSeek 时需要配置 deepseek_api_key")
        # DeepSeek 推理模型（如 deepseek-reasoner）通过 model 名称区分
        return ChatDeepSeek(
            api_key=config.deepseek_api_key,
            **kwargs,
        )

    return ChatZhipuAI(
        api_key=config.zhipu_api_key,
        **kwargs,
    )
