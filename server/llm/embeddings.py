"""嵌入模型模块。

智能解析 embedding 模型：
1. 如果 configuration embedding_model 已设置（如 "siliconflow/bge-large-zh"），直接使用
2. 否则从 chat 厂商的 models 中查找 embedding 类模型
3. 找不到则报错，提示用户配置

多模态支持：当 embedding 模型为多模态（如 jina-clip-v2）时，
返回 MultimodalEmbeddings，能同时处理文本和 [IMAGE] 标记的图片 Document。
"""

from typing import Any

import openai
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

from server.core.config import RAGConfig, _split_model_ref
from server.core.logging_config import get_logger

logger = get_logger(__name__)

# embedding 模型名称关键词
_EMBED_KEYWORDS = ["embedding", "text-embedding", "bge-", "e5-", "gte-", "clip"]
# 纯文本时排除的视觉模型关键词
_EMBED_EXCLUDE = ["vl-embedding", "vl-", "vision-embedding", "multimodal-embedding"]
# 正向判定多模态模型的关键词（能同时处理文字 + 图片）
_MULTIMODAL_KEYWORDS = ["clip", "multimodal-embedding", "vl-embedding"]


class MultimodalEmbeddings(BaseModel, Embeddings):
    """多模态嵌入模型，支持文本和图片混合输入。

    Document.page_content 以 "[IMAGE]\\n" 开头时识别为图片嵌入，
    其余按普通文本处理。
    """

    model: str
    api_key: str = Field(repr=False)
    base_url: str = ""

    class Config:
        arbitrary_types_allowed = True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """嵌入文档列表，支持文本/图片混合。

        Qwen3-VL-Embedding 要求图片用 {\"image\": \"data:...\"} 格式，
        纯文本用普通字符串。
        """
        inputs: list[Any] = [
            {"image": t[len("[IMAGE]\n"):]} if t.startswith("[IMAGE]\n") else t
            for t in texts
        ]

        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        resp = client.embeddings.create(model=self.model, input=inputs)

        # 按 index 排序后提取 embedding
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]

    def embed_query(self, text: str) -> list[float]:
        """嵌入查询文本（始终为纯文本）。"""
        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        resp = client.embeddings.create(model=self.model, input=[text])
        return resp.data[0].embedding


def _is_multimodal_model(model_name: str) -> bool:
    """判断是否为多模态 embedding 模型。"""
    ml = model_name.lower()
    return any(kw in ml for kw in _MULTIMODAL_KEYWORDS)


def _find_embedding_model(provider_models: list[str]) -> str | None:
    """从厂商模型列表中找第一个纯文本 embedding 模型。"""
    for m in provider_models:
        ml = m.lower()
        if any(kw in ml for kw in _EMBED_KEYWORDS) and not any(ex in ml for ex in _EMBED_EXCLUDE):
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
        "（如 zhipuai/embedding-3、siliconflow/bge-large-zh 等），然后在设置中指定 embedding_model。"
    )


def get_embeddings(config: RAGConfig | None = None):
    """获取嵌入模型实例。

    优先级：
    1. 自定义向量模型配置（embedding_custom.enabled）
    2. 显式配置的 embedding_model（provider/model）
    3. 从 chat 厂商查找 embedding 类模型
    4. 遍历所有有 api_key 的厂商查找

    多模态模型（如 jina-clip-v2）返回 MultimodalEmbeddings，
    纯文本模型返回 OpenAIEmbeddings。
    """
    config = config or RAGConfig.from_settings()

    # 0. 自定义向量模型配置（独立 base_url / api_key / model）
    custom = config.embedding_custom or {}
    if custom.get("enabled") and custom.get("model") and custom.get("api_key"):
        base_url = custom.get("base_url", "")
        model = custom["model"]
        if _is_multimodal_model(model):
            logger.info("使用自定义多模态向量模型: %s", model)
            return MultimodalEmbeddings(
                api_key=custom["api_key"],
                model=model,
                base_url=base_url,
            )
        kwargs = {"api_key": custom["api_key"], "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        logger.info("使用自定义向量模型: %s (base_url=%s)", model, base_url or "默认")
        return OpenAIEmbeddings(**kwargs)

    try:
        provider, model, api_key = resolve_embedding(config)
    except ValueError:
        raise

    base_url = config.providers.get(provider, {}).get("base_url", "")

    if _is_multimodal_model(model):
        logger.info("使用多模态向量模型: %s/%s", provider, model)
        return MultimodalEmbeddings(api_key=api_key, model=model, base_url=base_url)

    kwargs = {"api_key": api_key, "model": model}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs)


def get_embedding_dim(embeddings) -> int:
    """通过实际调用 embedding 模型来获取向量维度。

    支持 OpenAIEmbeddings 和 MultimodalEmbeddings。

    Args:
        embeddings: Embedding 实例

    Returns:
        向量维度，失败返回 0
    """
    try:
        vec = embeddings.embed_query("dim check")
        return len(vec)
    except Exception as e:
        logger.warning("无法检测 embedding 维度: %s", e)
        return 0
