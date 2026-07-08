"""大语言模型模块。

从 config.providers 获取厂商 API Key / base_url，构建 Chat 模型。
预设厂商（deepseek/zhipuai）用专用 LangChain 类，其他用 ChatOpenAI 通用适配。
"""

from langchain_community.chat_models import ChatZhipuAI
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from server.core.config import RAGConfig

_providers: dict[str, callable] = {}


def register_provider(name: str):
    def decorator(func):
        _providers[name] = func
        return func
    return decorator


def _build_kwargs(config: RAGConfig) -> dict:
    kwargs: dict = {
        "model": config.chat_model,
        "temperature": config.temperature,
        "timeout": config.timeout,
        "streaming": True,
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
    api_key = config.deepseek_api_key or config.get_active_api_key()
    if not api_key:
        raise ValueError("DeepSeek 需要配置 api_key")
    return ChatDeepSeek(api_key=api_key, **_build_kwargs(config))


@register_provider("zhipuai")
def _build_zhipuai(config: RAGConfig):
    api_key = config.zhipu_api_key or config.get_active_api_key()
    return ChatZhipuAI(api_key=api_key, **_build_kwargs(config))


def get_chat_model(config: RAGConfig | None = None):
    """根据配置获取聊天模型实例。

    预设厂商走注册表（DeepSeek → ChatDeepSeek, 智谱 → ChatZhipuAI），
    自定义厂商用 ChatOpenAI + config.providers 中的 base_url / api_key。
    """
    config = config or RAGConfig.from_settings()

    builder = _providers.get(config.chat_provider)
    if builder is not None:
        return builder(config)

    # 自定义厂商：从 providers 获取 api_key + base_url
    prov = config.providers.get(config.chat_provider, {})
    api_key = prov.get("api_key", "")
    base_url = prov.get("base_url", "")

    if not api_key:
        raise ValueError(
            f"厂商 {config.chat_provider} 未配置 API Key，"
            f"请在设置中填写"
        )

    kwargs = _build_kwargs(config)
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(api_key=api_key, **kwargs)


def test_model_connectivity(
    provider_id: str,
    model: str,
    api_key: str,
    base_url: str = "",
    timeout: int = 15,
) -> dict:
    """快速测试模型联通性。发一个最短 chat 请求。
    返回 {"ok": true, "latency_ms": 760} 或 {"ok": false, "error": "..."}。
    """
    import time
    from langchain_core.messages import HumanMessage
    from copy import deepcopy

    # vision 模型不接受纯文本，直接跳过并给出说明
    ml = model.lower()
    if "vision" in ml or "vl-" in ml or "video" in ml:
        return {"ok": False, "error": "视觉模型不支持纯文本测试"}

    cfg = RAGConfig.from_settings()
    cfg.active_model = f"{provider_id}/{model}"
    cfg.providers = deepcopy(cfg.providers)
    if provider_id not in cfg.providers:
        cfg.providers[provider_id] = {}
    cfg.providers[provider_id]["api_key"] = api_key
    if base_url:
        cfg.providers[provider_id]["base_url"] = base_url
    cfg.timeout = timeout
    cfg.max_tokens = 10
    cfg.enable_thinking = False
    cfg.reasoning_effort = None
    cfg.temperature = 0.5           # 多数模型默认值，不兼容时回退到 None
    cfg.top_p = None
    cfg.frequency_penalty = None
    cfg.presence_penalty = None

    for attempt in range(2):
        try:
            llm = get_chat_model(cfg)
            if hasattr(llm, 'streaming'):
                llm.streaming = False

            t0 = time.perf_counter()
            resp = llm.invoke([HumanMessage(content="hi")], config={"timeout": timeout})
            elapsed = (time.perf_counter() - t0) * 1000

            return {"ok": True, "latency_ms": round(elapsed)}
        except Exception as exc:
            if attempt == 0:
                # 第一次失败 → 重试：temperature=1.0 (kimi-k2 等模型要求)
                cfg.temperature = 1.0
                cfg.enable_thinking = False
                cfg.reasoning_effort = None
                continue
            error_msg = str(exc)[:300]
            if "400" in error_msg or "Bad Request" in error_msg:
                error_msg = f"参数不兼容 ({error_msg[:200]})"
            return {"ok": False, "error": error_msg}
    return {"ok": False, "error": "未知错误"}
