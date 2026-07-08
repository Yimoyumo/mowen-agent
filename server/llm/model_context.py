"""模型上下文窗口映射表。

数据来源：各厂商官网（2026-07-06 核实）
- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing
- 智谱 GLM: https://bigmodel.cn/pricing
- Kimi:     https://platform.kimi.com/docs/models
- Qwen:     https://help.aliyun.com/zh/model-studio/text-generation-model/
- OpenAI:   https://platform.openai.com/docs/models

context_window = 输入 + 输出的总 token 上限
max_output = 模型单次最大输出 token 数
"""

# 格式: "model_name": (context_window, max_output)
# model_name 统一小写，匹配时也用小写
_MODEL_CONTEXT = {
    # ==================== DeepSeek ====================
    # 官网: context 1M, max output 384K
    "deepseek-v4-flash": (1_048_576, 393_216),
    "deepseek-v4-pro": (1_048_576, 393_216),
    # deepseek-chat / deepseek-reasoner 即将弃用，对应 v4-flash 的非思考/思考模式
    "deepseek-chat": (1_048_576, 8_192),
    "deepseek-reasoner": (1_048_576, 65_536),
    # 旧版
    "deepseek-v3": (163_840, 8_192),
    "deepseek-v3.1": (163_840, 163_840),
    "deepseek-v3.2": (163_840, 163_840),
    "deepseek-r1": (163_840, 163_840),

    # ==================== 智谱 GLM ====================
    # 官网定价页
    "glm-5.2": (1_048_576, 1_048_576),
    "glm-5.1": (198_000, 65_535),
    "glm-5": (198_000, 65_535),
    "glm-5-turbo": (198_000, 65_535),
    "glm-4.7": (200_000, 128_000),
    "glm-4.7-flash": (200_000, 32_000),
    "glm-4.7-flashx": (200_000, 32_000),
    "glm-4.6": (200_000, 131_072),
    "glm-4.5": (128_000, 131_072),
    "glm-4.5-air": (128_000, 98_304),
    "glm-4-plus": (128_000, 4_096),
    "glm-4-air": (128_000, 4_096),
    "glm-4-airx": (8_000, 0),
    "glm-4-flash": (128_000, 4_096),
    "glm-4-flashx": (128_000, 4_096),
    "glm-4-long": (1_048_576, 4_096),

    # ==================== 月之暗面 Kimi ====================
    # 官网模型列表
    "kimi-k2.7-code": (262_144, 262_144),
    "kimi-k2.7-code-highspeed": (262_144, 262_144),
    "kimi-k2.6": (262_144, 262_144),
    "kimi-k2.5": (262_144, 262_144),
    # 已下线但保留兼容
    "kimi-k2": (131_072, 16_384),
    "kimi-k2-thinking": (262_144, 262_144),
    # Moonshot V1 系列
    "moonshot-v1-8k": (8_192, 8_192),
    "moonshot-v1-32k": (32_768, 32_768),
    "moonshot-v1-128k": (131_072, 131_072),
    "moonshot-v1-auto": (131_072, 131_072),

    # ==================== 通义千问 Qwen ====================
    # 阿里百炼官网
    "qwen3.7-max": (1_048_576, 8_192),
    "qwen3.7-plus": (1_048_576, 16_384),
    "qwen3.6-flash": (1_048_576, 16_384),
    "qwen3.6-max-preview": (262_144, 8_192),
    "qwen3.6-plus": (1_048_576, 16_384),
    "qwen3.5-plus": (1_048_576, 16_384),
    "qwen3.5-flash": (1_048_576, 16_384),
    "qwen3-max": (262_144, 8_192),
    "qwen-plus": (1_048_576, 16_384),
    "qwen-turbo": (131_072, 16_384),
    "qwen-max": (32_768, 8_192),
    "qwen-flash": (1_048_576, 32_768),
    "qwen-long": (10_485_760, 8_192),

    # ==================== OpenAI ====================
    # 官网 models 页
    "gpt-4.1": (1_047_576, 32_768),
    "gpt-4.1-mini": (1_047_576, 32_768),
    "gpt-4.1-nano": (1_047_576, 32_768),
    "gpt-4o": (128_000, 16_384),
    "gpt-4o-mini": (128_000, 16_384),
    "gpt-4o-mini": (128_000, 16_384),
    "gpt-4-turbo": (128_000, 4_096),
    "gpt-4": (8_192, 4_096),
    "gpt-4-32k": (32_768, 4_096),
    "o1": (200_000, 100_000),
    "o1-mini": (128_000, 65_536),
    "o3": (200_000, 100_000),
    "o3-mini": (200_000, 100_000),
    "o4-mini": (200_000, 100_000),
}


def _fuzzy_match(model_name: str) -> tuple[int, int] | None:
    """模糊匹配模型名，返回 (context_window, max_output) 或 None。

    匹配策略：
    1. 精确匹配
    2. 去掉版本后缀（-2025-04-14 等）
    3. 前缀匹配（如 deepseek-ai/DeepSeek-V3 → deepseek-v3）
    """
    name = model_name.lower().strip()

    # 1. 精确匹配
    if name in _MODEL_CONTEXT:
        return _MODEL_CONTEXT[name]

    # 2. 去掉日期后缀: gpt-4o-2024-08-06 → gpt-4o
    import re
    stripped = re.sub(r'-\d{4}-\d{2}-\d{2}.*$', '', name)
    if stripped != name and stripped in _MODEL_CONTEXT:
        return _MODEL_CONTEXT[stripped]

    # 3. 去掉厂商前缀: deepseek-ai/deepseek-v3 → deepseek-v3
    if '/' in name:
        bare = name.split('/')[-1]
        if bare in _MODEL_CONTEXT:
            return _MODEL_CONTEXT[bare]
        # 尝试去掉 deepseek-ai/ 等前缀后的名字
        for prefix in ('deepseek-ai/', 'qwen/', 'qwen/', 'zai-org/', 'moonshotai/'):
            if name.startswith(prefix):
                bare = name[len(prefix):]
                if bare in _MODEL_CONTEXT:
                    return _MODEL_CONTEXT[bare]

    # 4. 前缀匹配: glm-4-flash-250414 → glm-4-flash
    for key in _MODEL_CONTEXT:
        if name.startswith(key) or key.startswith(name):
            return _MODEL_CONTEXT[key]

    return None


def get_model_context_window(model_name: str) -> int:
    """获取模型上下文窗口大小（token 数）。

    Args:
        model_name: 模型名称，如 "deepseek-v4-flash" 或 "deepseek/deepseek-v4-flash"

    Returns:
        上下文窗口 token 数，未知模型返回 0
    """
    # 去掉 provider/ 前缀
    if '/' in model_name:
        model_name = model_name.split('/')[-1]

    result = _fuzzy_match(model_name)
    if result:
        return result[0]
    return 0


def get_model_max_output(model_name: str) -> int:
    """获取模型最大输出 token 数。

    Args:
        model_name: 模型名称

    Returns:
        最大输出 token 数，未知模型返回 0
    """
    if '/' in model_name:
        model_name = model_name.split('/')[-1]

    result = _fuzzy_match(model_name)
    if result:
        return result[1]
    return 0


def get_model_info(model_name: str) -> dict:
    """获取模型完整信息。

    Returns:
        {"context_window": int, "max_output": int}
        未知模型返回 {"context_window": 0, "max_output": 0}
    """
    if '/' in model_name:
        model_name = model_name.split('/')[-1]

    result = _fuzzy_match(model_name)
    if result:
        return {"context_window": result[0], "max_output": result[1]}
    return {"context_window": 0, "max_output": 0}


# ==================== 用户自定义覆盖 ====================

def _load_user_overrides() -> dict:
    """从 user_settings.json 读取 model_context_overrides 字段。

    格式:
        {
            "deepseek/deepseek-v4-flash": {"context_window": 2000000, "max_output": 384000},
            "custom_abc/some-model": {"context_window": 32768, "max_output": 4096}
        }
    """
    try:
        from server.core.user_settings import user_settings
        settings = user_settings.load()
        return settings.get("model_context_overrides", {})
    except Exception:
        return {}


def get_model_info_with_overrides(model_ref: str) -> dict:
    """获取模型完整信息（支持用户自定义覆盖）。

    优先级：用户自定义覆盖 > 内置映射表 > 返回 0

    Args:
        model_ref: 完整模型引用，如 "deepseek/deepseek-v4-flash"

    Returns:
        {"context_window": int, "max_output": int, "source": "override"|"builtin"|"unknown"}
    """
    # 1. 先查用户自定义覆盖
    overrides = _load_user_overrides()
    if model_ref in overrides:
        o = overrides[model_ref]
        return {
            "context_window": o.get("context_window", 0),
            "max_output": o.get("max_output", 0),
            "has_vision": o.get("has_vision", False),
            "source": "override",
        }

    # 2. 再查内置映射表
    bare_name = model_ref.split("/")[-1] if "/" in model_ref else model_ref
    result = _fuzzy_match(bare_name)
    if result:
        return {
            "context_window": result[0],
            "max_output": result[1],
            "has_vision": False,
            "source": "builtin",
        }

    return {"context_window": 0, "max_output": 0, "has_vision": False, "source": "unknown"}


def get_model_generation_overrides(model_ref: str) -> dict:
    """获取模型级别的 generation 参数覆盖。

    从 model_context_overrides 中提取 generation 相关字段。
    只返回实际设置了覆盖值的字段。

    Returns:
        可能包含的 key: temperature, max_tokens, thinking, reasoning_effort
        例: {"temperature": 0.7, "thinking": False}
        无覆盖时返回 {}
    """
    overrides = _load_user_overrides()
    entry = overrides.get(model_ref, {})
    result = {}
    for k in ("temperature", "max_tokens", "thinking", "reasoning_effort"):
        if k in entry:
            result[k] = entry[k]
    return result
