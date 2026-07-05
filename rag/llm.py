"""大语言模型模块。

支持多厂商 Chat 模型，通过配置切换。
当前支持：DeepSeek（deepseek-chat / deepseek-reasoner）和 智谱 AI（GLM 系列）。

添加新厂商：只需写一个 @register_provider 函数，无需改工厂函数。
"""

from langchain_community.chat_models import ChatZhipuAI
from langchain_deepseek import ChatDeepSeek

from rag.config import RAGConfig

# 厂商注册表
_providers: dict[str, callable] = {}


def register_provider(name: str):
    """装饰器：将函数注册为指定厂商的 Chat 模型构建器。"""
    def decorator(func):
        _providers[name] = func
        return func
    return decorator


def _build_kwargs(config: RAGConfig) -> dict:
    """根据配置构造通用的 LLM 调用参数。

    只包含非 None 的可选参数，避免覆盖各厂商的默认值。
    """
    kwargs: dict = {
        "model": config.chat_model,
        "temperature": config.temperature,
        "timeout": config.timeout,
        "streaming": True,  # 始终启用流式，底层由 astream/ainvoke 控制实际行为
    }
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    if config.top_p is not None:
        kwargs["top_p"] = config.top_p
    if config.frequency_penalty is not None:
        kwargs["frequency_penalty"] = config.frequency_penalty
    if config.presence_penalty is not None:
        kwargs["presence_penalty"] = config.presence_penalty
    if config.reasoning_effort is not None:
        kwargs["reasoning_effort"] = config.reasoning_effort
    return kwargs


@register_provider("deepseek")
def _build_deepseek(config: RAGConfig):
    """构建 DeepSeek Chat 模型。"""
    if not config.deepseek_api_key:
        raise ValueError("使用 DeepSeek 时需要配置 deepseek_api_key")
    return ChatDeepSeek(
        api_key=config.deepseek_api_key,
        **_build_kwargs(config),
    )


@register_provider("zhipuai")
def _build_zhipuai(config: RAGConfig):
    """构建智谱 AI Chat 模型。"""
    return ChatZhipuAI(
        api_key=config.zhipu_api_key,
        **_build_kwargs(config),
    )


def get_chat_model(config: RAGConfig | None = None):
    """根据配置获取聊天模型实例。

    根据 config.chat_provider 从注册表中查找对应的构建器。
    """
    config = config or RAGConfig.from_json()
    builder = _providers.get(config.chat_provider)
    if builder is None:
        raise ValueError(
            f"不支持的对话厂商: {config.chat_provider}，"
            f"已注册: {list(_providers.keys())}"
        )
    return builder(config)
