"""嵌入模型模块。

智能解析 embedding 模型：
1. 如果 configuration embedding_model 已设置（如 "zhipuai/embedding-3"），直接使用
2. 否则从 chat 厂商的 models 中查找 embedding 类模型
3. 找不到则报错，提示用户配置
"""

from langchain_community.embeddings import ZhipuAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from server.core.config import RAGConfig, _split_model_ref
from server.core.logging_config import get_logger

logger = get_logger(__name__)

# embedding 模型名称关键词
_EMBED_KEYWORDS = ["embedding", "text-embedding", "bge-", "e5-", "gte-"]


def _find_embedding_model(provider_models: list[str]) -> str | None:
    """从厂商模型列表中找第一个 embedding 模型。"""
    for m in provider_models:
        ml = m.lower()
        if any(kw in ml for kw in _EMBED_KEYWORDS):
            return m
    return None


def resolve_embedding(config: RAGConfig) -> tuple[str, str, str]:
    """解析 embedding 的 provider / model / api_key。

    Returns:
        (provider_id, model_name, api_key)

    Raises:
        ValueError: 找不到可用 embedding 模型
    """
    # 1. embedding_model 已显式配置
    if config.embedding_model and "/" in config.embedding_model:
        ep, em = _split_model_ref(config.embedding_model)
        key = config.providers.get(ep, {}).get("api_key", "") or config.get_embedding_api_key()
        if key:
            return ep, em, key

    # 2. 从 chat 厂商找 embedding
    cp = config.chat_provider
    if cp and cp in config.providers:
        models = config.providers[cp].get("models", [])
        embed_model = _find_embedding_model(models)
        if embed_model:
            key = config.providers[cp].get("api_key", "")
            if key:
                logger.info("自动从 %s 找到 embedding: %s", cp, embed_model)
                return cp, embed_model, key

    # 3. 遍历所有有 api_key 的厂商
    for pid, pdata in config.providers.items():
        key = pdata.get("api_key", "")
        if not key:
            continue
        models = pdata.get("models", [])
        embed_model = _find_embedding_model(models)
        if embed_model:
            logger.info("从 %s 找到 embedding: %s", pid, embed_model)
            return pid, embed_model, key

    raise ValueError(
        "未找到可用的 Embedding 模型。请在设置中为至少一个厂商填写 API Key 并确保其模型列表中有 embedding 类模型"
        "（如 zhipuai/embedding-3、deepseek/text-embedding 等），然后在设置中指定 embedding_model。"
    )


def get_embeddings(config: RAGConfig | None = None):
    """获取嵌入模型实例。

    自动解析 embedding 模型，优先使用配置的、其次从 chat 厂商找、最后遍历所有厂商。
    """
    config = config or RAGConfig.from_settings()

    try:
        provider, model, api_key = resolve_embedding(config)
    except ValueError:
        raise

    # 智谱用专用类
    if provider == "zhipuai":
        return ZhipuAIEmbeddings(api_key=api_key, model=model)

    # 其他厂商用 OpenAI 兼容
    base_url = config.providers.get(provider, {}).get("base_url", "")
    kwargs = {"api_key": api_key, "model": model}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs)
