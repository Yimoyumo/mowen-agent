"""厂商配置与模型拉取模块。

从 user_settings.json 读取预设厂商，从 API 拉取模型列表。

用法：
    from server.llm.provider_config import list_preset_providers, fetch_models
    providers = list_preset_providers()
    models = fetch_models("deepseek", api_key="sk-xxx")
"""

import requests

from server.core.config import RAGConfig
from server.core.logging_config import get_logger

logger = get_logger(__name__)

# 拉取失败时的回退列表
_FALLBACK_MODELS: dict[str, list[str]] = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "zhipuai": ["glm-4-flash", "glm-4-plus", "glm-4-flashx"],
    "siliconflow": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen3-235B-A22B"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "dashscope": ["qwen-plus", "qwen-max", "qwen-turbo"],
    "openai": ["gpt-4.1", "gpt-4o", "gpt-4o-mini"],
}


def list_preset_providers() -> list[dict]:
    """从 user_settings 获取所有 preset=true 的厂商。"""
    cfg = RAGConfig.from_settings()
    return cfg.list_preset_providers()


def get_fallback_models(provider_id: str) -> list[str]:
    """获取厂商的默认模型列表（拉取失败时回退）。"""
    return _FALLBACK_MODELS.get(provider_id, [])


def fetch_models(
    provider_id: str,
    api_key: str,
    base_url: str | None = None,
    timeout: int = 15,
) -> list[str]:
    """从厂商 API 拉取可用模型列表（GET {base_url}/models）。

    优先用传入的 base_url，否则从 user_settings providers 读取。
    失败时返回 _FALLBACK_MODELS 中的默认列表。
    """
    if not base_url:
        cfg = RAGConfig.from_settings()
        base_url = cfg.get_provider_base_url(provider_id)

    if not base_url:
        logger.warning("厂商 %s 无 base_url，无法拉取模型列表", provider_id)
        return []

    url = base_url.rstrip("/") + "/models"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            models = _parse_models(data)
            if models:
                logger.info("从 %s 拉取到 %d 个模型: %s…", provider_id, len(models), ", ".join(models[:5]))
                return models
            logger.warning("%s /models 返回空列表", provider_id)
        elif resp.status_code == 401:
            logger.warning("%s API Key 无效 (401)", provider_id)
        elif resp.status_code == 404:
            logger.warning("%s 不支持 /models 端点 (404)", provider_id)
        else:
            logger.warning("%s /models 返回 %d: %s", provider_id, resp.status_code, resp.text[:200])
    except requests.Timeout:
        logger.warning("拉取 %s 模型列表超时 (%ds)", provider_id, timeout)
    except requests.RequestException as exc:
        logger.warning("拉取 %s 模型列表失败: %s", provider_id, exc)

    fallback = get_fallback_models(provider_id)
    if fallback:
        logger.info("使用 %s 预设模型列表回退: %s", provider_id, fallback)
    return fallback


def _parse_models(data: dict) -> list[str]:
    """解析 /models 返回的 JSON，提取模型 ID 列表。

    支持 OpenAI 兼容格式：{"data": [{"id": "gpt-4"}, ...]}
    也支持智谱格式：{"data": [{"id": "glm-4-flash"}, ...]}
    """
    items = data.get("data", [])
    if not isinstance(items, list):
        return []

    models = []
    for item in items:
        if isinstance(item, dict):
            mid = item.get("id", "")
            if mid:
                models.append(mid)
    return models
