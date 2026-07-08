"""用户设置路由。

提供模型选择、检索参数、人格设定、用户画像等的增删查改 API。

路由：
- GET    /api/settings                  获取所有用户设置
- PUT    /api/settings                  更新用户设置（部分更新）
- POST   /api/settings/reset            重置为默认设置

- GET    /api/settings/providers        获取所有可选厂商（预设 + 自定义）
- POST   /api/settings/providers        添加自定义厂商
- PUT    /api/settings/providers/{id}   更新厂商（填 API Key / 选模型）
- DELETE /api/settings/providers/{id}   删除自定义厂商
- POST   /api/settings/providers/{id}/fetch  拉取厂商模型列表
- PUT    /api/settings/model            设置当前使用的模型

- GET    /api/settings/profile          获取用户画像
- PUT    /api/settings/profile          更新用户画像
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import NotFoundError, ValidationError
from server.provider_config import list_preset_providers, fetch_models, get_fallback_models
from server.user_settings import user_settings
from server.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ==================== 请求模型 ====================

class UserProfileUpdate(BaseModel):
    """用户画像更新。"""
    skills: str = ""
    interests: str = ""
    preferences: str = ""


class ProviderUpdate(BaseModel):
    """厂商更新。"""
    api_key: str = ""          # API Key（空 = 不修改）
    base_url: str = ""         # 自定义厂商的 base_url（预设厂商忽略）


class AddCustomProvider(BaseModel):
    """添加自定义厂商。"""
    name: str                  # 显示名称
    base_url: str              # API 地址，如 https://api.openai.com/v1
    api_key: str = ""          # API Key（可选，可不填）


class SetModelRequest(BaseModel):
    """设置当前模型。"""
    model: str                 # "provider/model"


class ModelContextOverride(BaseModel):
    """设置模型上下文窗口覆盖。"""
    context_window: int       # 上下文窗口大小（token 数）
    max_output: int = 0        # 最大输出 token 数（可选）


# ==================== 全局设置 ====================


@router.get("/settings")
def get_settings() -> dict:
    """获取所有用户设置。"""
    return user_settings.load()


@router.put("/settings")
def update_settings(updates: dict) -> dict:
    """更新用户设置（部分更新，支持嵌套）。"""
    if not updates:
        raise ValidationError("更新内容不能为空")
    updated = user_settings.update(updates)
    logger.info("用户设置已更新")
    return {"status": "ok", "settings": updated}


@router.post("/settings/reset")
def reset_settings() -> dict:
    """重置所有设置为默认值。"""
    defaults = user_settings.reset()
    return {"status": "ok", "settings": defaults}


# ==================== 厂商管理 ====================


@router.get("/settings/providers")
def get_providers() -> dict:
    """获取所有可选厂商：预设 + 自定义厂商 + 当前选中状态。"""
    presets = list_preset_providers()
    settings = user_settings.load()
    providers_config = settings.get("providers", {})

    custom_list = []
    for pid, pdata in providers_config.items():
        is_preset = any(pp["id"] == pid for pp in presets)
        if is_preset:
            continue
        custom_list.append({
            "id": pid,
            "name": pdata.get("name", pid),
            "base_url": pdata.get("base_url", ""),
            "desc": pdata.get("desc", "自定义厂商"),
            "preset": False,
            "has_api_key": bool(pdata.get("api_key", "")),
            "models": pdata.get("models", []),
            "selected_model": pdata.get("selected_model", ""),
        })

    # 补充预设厂商的 API key / 模型（来自用户 settings）
    for p in presets:
        pid = p["id"]
        prov = providers_config.get(pid, {})
        p["has_api_key"] = bool(prov.get("api_key", ""))
        p["models"] = prov.get("models") or get_fallback_models(pid)

    current_model = settings.get("active_model", "")
    # 兜底：如果用户没设，用默认值
    if not current_model:
        from server.user_settings import _DEFAULT_SETTINGS
        current_model = _DEFAULT_SETTINGS.get("active_model", "")

    return {
        "providers": presets + custom_list,
        "active_model": current_model,
    }


@router.post("/settings/providers")
def add_custom_provider(item: AddCustomProvider) -> dict:
    """添加自定义厂商（OpenAI 兼容 API）。"""
    if not item.name.strip():
        raise ValidationError("厂商名称不能为空")
    if not item.base_url.strip():
        raise ValidationError("base_url 不能为空")

    pid = f"custom_{uuid.uuid4().hex[:8]}"

    settings = user_settings.load()
    providers = settings.setdefault("providers", {})
    providers[pid] = {
        "name": item.name.strip(),
        "base_url": item.base_url.strip(),
        "api_key": item.api_key.strip(),
        "models": [],
    }
    user_settings.save(settings)

    logger.info("自定义厂商已添加: %s (%s)", item.name, pid)
    return {
        "status": "ok",
        "provider": {"id": pid, "name": item.name, "base_url": item.base_url, "preset": False},
    }


@router.put("/settings/providers/{provider_id}")
def update_provider(provider_id: str, item: ProviderUpdate) -> dict:
    """更新厂商配置（填 API Key / 选模型）。"""
    settings = user_settings.load()
    providers = settings.setdefault("providers", {})

    if provider_id not in providers:
        providers[provider_id] = {"models": [], "api_key": "", "base_url": ""}

    prov = providers[provider_id]

    if item.api_key:
        prov["api_key"] = item.api_key.strip()

    if item.base_url and not _is_preset_provider(provider_id):
        prov["base_url"] = item.base_url.strip()

    user_settings.save(settings)

    logger.info("厂商已更新: %s | has_api_key=%s", provider_id, bool(prov.get("api_key")))
    return {"status": "ok", "message": "厂商已更新"}


@router.delete("/settings/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict:
    """删除自定义厂商（预设厂商不可删除）。"""
    if _is_preset_provider(provider_id):
        raise ValidationError("预设厂商不可删除")

    settings = user_settings.load()
    providers = settings.get("providers", {})

    if provider_id not in providers:
        raise NotFoundError("厂商不存在")

    del providers[provider_id]

    if settings.get("active_model", "").startswith(f"{provider_id}/"):
        settings["active_model"] = ""

    user_settings.save(settings)
    logger.info("自定义厂商已删除: %s", provider_id)
    return {"status": "ok", "message": "厂商已删除"}


@router.post("/settings/providers/{provider_id}/fetch")
def fetch_provider_models(provider_id: str, body: dict = None) -> dict:
    """拉取厂商的可用模型列表。

    从厂商的 /models 端点获取模型 ID 列表，缓存到 settings 中。

    Request body（可选）:
        {"api_key": "sk-xxx"}  临时指定 API Key，留空则从已保存的设置读取
    """
    settings = user_settings.load()
    providers = settings.get("providers", {})

    # 查找 API key
    api_key = (body or {}).get("api_key", "").strip()
    if not api_key and provider_id in providers:
        api_key = providers[provider_id].get("api_key", "")

    # 预设厂商的 api_key 也可从预设配置兜底
    if not api_key:
        api_key = _get_fallback_api_key(provider_id)

    if not api_key:
        raise ValidationError("请先填写 API Key")

    # 获取 base_url（优先用户设置，其次预设配置）
    base_url = None
    if provider_id in providers:
        base_url = providers[provider_id].get("base_url")
    if not base_url:
        cfg = RAGConfig.from_settings()
        base_url = cfg.get_provider_base_url(provider_id)

    try:
        models = fetch_models(provider_id, api_key, base_url=base_url)
    except Exception as exc:
        raise ValidationError(f"拉取模型列表失败: {exc}")

    if not models:
        return {"status": "ok", "models": [], "message": "未能获取模型列表，请确认 API Key 有效"}

    # 缓存到 providers.{id}.models
    if provider_id not in providers:
        providers[provider_id] = {}
    providers[provider_id]["models"] = models
    settings["providers"] = providers
    user_settings.save(settings)

    return {"status": "ok", "models": models, "count": len(models)}


@router.put("/settings/model")
def set_current_model(body: SetModelRequest) -> dict:
    """设置当前使用的模型，格式 'provider/model'。"""
    model_ref = body.model.strip()
    if "/" not in model_ref:
        raise ValidationError("模型格式必须为 provider/model")
    user_settings.set_active_model(model_ref)
    logger.info("当前模型已切换: %s", model_ref)
    return {"status": "ok", "active_model": model_ref}


@router.post("/settings/providers/{provider_id}/test")
def test_provider_model(provider_id: str, body: dict) -> dict:
    """测试模型联通性。Request body: {"model": "deepseek-v4-pro"}"""
    model = (body or {}).get("model", "").strip()
    if not model:
        raise ValidationError("请指定要测试的模型")

    settings = user_settings.load()
    providers = settings.get("providers", {})
    api_key = providers.get(provider_id, {}).get("api_key", "")
    if not api_key:
        api_key = _get_fallback_api_key(provider_id)
    if not api_key:
        raise ValidationError("请先填写 API Key")

    base_url = providers.get(provider_id, {}).get("base_url", "")

    from server.llm import test_model_connectivity
    result = test_model_connectivity(provider_id, model, api_key, base_url=base_url)
    if result["ok"]:
        logger.info("模型联通: %s/%s %.0fms", provider_id, model, result["latency_ms"])
    else:
        logger.warning("模型联通失败: %s/%s %s", provider_id, model, result["error"])
    return result


# ==================== 用户画像 ====================

@router.get("/settings/profile")
def get_profile() -> dict:
    """获取用户画像。"""
    settings = user_settings.load()
    return settings.get("user_profile", {
        "skills": "", "interests": "", "preferences": "",
    })


@router.put("/settings/profile")
def update_profile(profile: UserProfileUpdate) -> dict:
    """更新用户画像。"""
    settings = user_settings.load()
    settings["user_profile"] = {
        "skills": profile.skills.strip(),
        "interests": profile.interests.strip(),
        "preferences": profile.preferences.strip(),
    }
    user_settings.save(settings)
    logger.info("用户画像已更新")
    return {"status": "ok", "profile": settings["user_profile"]}


# ==================== 模型上下文窗口 ====================

@router.get("/settings/model-context")
def get_model_context(model: str = "") -> dict:
    """获取模型的上下文窗口信息。

    Query params:
        model: 模型引用，如 "deepseek/deepseek-v4-flash"。不传则返回当前选中模型。

    优先级：用户自定义覆盖 > 内置映射表 > 未知(0)
    """
    from server.model_context import get_model_info_with_overrides

    model_ref = model.strip()
    if not model_ref:
        settings = user_settings.load()
        model_ref = settings.get("active_model", "")

    info = get_model_info_with_overrides(model_ref)

    # 也返回 generation 覆盖（如果有）
    from server.model_context import get_model_generation_overrides
    gen_override = get_model_generation_overrides(model_ref)

    return {"model": model_ref, **info, "generation_override": gen_override, "has_vision": info.get("has_vision", False)}


@router.put("/settings/model-context")
def set_model_context_override(body: dict) -> dict:
    """为指定模型设置覆盖（上下文窗口 + 生成参数）。

    Body:
        {
            "model": "custom_abc/some-model",
            "context_window": 32768,         // 上下文窗口（token），>0 生效
            "max_output": 4096,               // 最大输出 token 数
            "temperature": 0.7,               // 生成温度（可选）
            "thinking": false,                // 思考模式（可选）
            "reasoning_effort": "medium",     // 推理强度（可选）
            "max_tokens": 8192                // 最大输出 token（可选）
        }
    """
    model_ref = (body or {}).get("model", "").strip()
    if not model_ref:
        raise ValidationError("model 不能为空")

    settings = user_settings.load()
    overrides = settings.setdefault("model_context_overrides", {})

    # 合并：保留已有覆盖值，用新值更新
    entry = overrides.get(model_ref, {})

    if "context_window" in body:
        entry["context_window"] = int(body["context_window"])
    if "max_output" in body:
        entry["max_output"] = int(body["max_output"])
    # 视觉能力（可选）
    if "has_vision" in body:
        entry["has_vision"] = bool(body["has_vision"])
    # generation 参数（可选覆盖）
    for k in ("temperature", "thinking", "reasoning_effort", "max_tokens"):
        if k in body:
            entry[k] = body[k]

    overrides[model_ref] = entry
    user_settings.save(settings)
    logger.info("模型覆盖已设置: %s → %s", model_ref, entry)
    return {"status": "ok", "model": model_ref, **entry}


@router.delete("/settings/model-context")
def delete_model_context_override(model: str) -> dict:
    """删除指定模型的上下文窗口覆盖。

    Query params:
        model: 模型引用，如 "custom_abc/some-model"
    """
    model_ref = model.strip()
    if not model_ref:
        raise ValidationError("model 不能为空")

    settings = user_settings.load()
    overrides = settings.get("model_context_overrides", {})

    if model_ref not in overrides:
        raise NotFoundError(f"模型 {model_ref} 没有自定义覆盖")

    del overrides[model_ref]
    if not overrides:
        settings.pop("model_context_overrides", None)
    else:
        settings["model_context_overrides"] = overrides

    user_settings.save(settings)
    logger.info("模型上下文覆盖已删除: %s", model_ref)
    return {"status": "ok", "model": model_ref}


@router.get("/settings/model-vision")
def get_model_vision_map() -> dict:
    """获取所有模型的视觉能力映射。

    返回: { "moonshot/kimi-k2.6": true, "deepseek/deepseek-v4": false, ... }
    前端用这个来决定是否显示 👁️ 视觉标记。
    """
    from server.model_context import get_model_info_with_overrides

    settings = user_settings.load()
    providers = settings.get("providers", {})

    result = {}
    for pid, pdata in providers.items():
        for model in pdata.get("models", []):
            ref = f"{pid}/{model}"
            info = get_model_info_with_overrides(ref)
            result[ref] = info.get("has_vision", False)

    return result


# ==================== 工具函数 ====================

_PRESET_IDS = {"deepseek", "zhipuai", "siliconflow", "moonshot", "dashscope", "openai"}


def _is_preset_provider(provider_id: str) -> bool:
    return provider_id in _PRESET_IDS


def _get_fallback_api_key(provider_id: str) -> str:
    """从 user_settings 获取 API key 兜底。"""
    settings = user_settings.load()
    prov = settings.get("providers", {}).get(provider_id, {})
    return prov.get("api_key", "")


# ==================== MCP & Skills 状态 ====================

@router.get("/settings/extensions")
def get_extensions() -> dict:
    """获取已配置的 MCP 服务器和已启用的技能列表。

    返回:
        {
            "mcp_servers": [{"name": "filesystem", "command": "npx", ...}],
            "skills": [{"name": "data_analysis", "description": "...", "available": true}]
        }
    """
    settings = user_settings.load()

    # MCP 服务器配置
    mcp_raw = settings.get("mcp_servers", {})
    mcp_servers = []
    for name, cfg in mcp_raw.items():
        transport = cfg.get("transport", cfg.get("type", "stdio"))
        mcp_servers.append({
            "name": name,
            "command": cfg.get("command", ""),
            "args": cfg.get("args", []),
            "transport": transport,
            "url": cfg.get("url", ""),
        })

    # 技能列表
    from server.agent.skills import load_skills_summary, list_available_skills
    skill_names = settings.get("skills", [])
    available = list_available_skills()
    skills = []
    for name in skill_names:
        skills.append({
            "name": name,
            "available": name in available,
        })

    return {
        "mcp_servers": mcp_servers,
        "skills": skills,
        "available_skills": available,
    }


@router.post("/settings/mcp-servers/test")
async def test_mcp_servers(body: dict = None) -> dict:
    """测试所有 MCP 服务器的连接状态。

    逐个连接每个 MCP 服务器，返回连接结果（成功/失败 + 工具数）。

    Returns:
        {"results": {"filesystem": {"ok": true, "tool_count": 14, "error": ""}, ...}}
    """
    import asyncio
    from server.agent.mcp import _load_single_server_tools

    settings = user_settings.load()
    mcp_raw = settings.get("mcp_servers", {})

    # 转换配置格式
    servers = {}
    for name, cfg in mcp_raw.items():
        transport = cfg.get("transport", cfg.get("type", "stdio"))
        if transport in ("stdio", "local"):
            servers[name] = {
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "transport": "stdio",
            }
        elif transport in ("sse", "remote", "streamable_http", "http"):
            actual = "http" if transport in ("streamable_http", "http") else "sse"
            servers[name] = {
                "url": cfg.get("url", ""),
                "transport": actual,
            }

    # 并发测试
    async def _test_one(name: str, cfg: dict) -> dict:
        try:
            tools = await asyncio.wait_for(
                _load_single_server_tools(name, cfg),
                timeout=15,
            )
            return {"ok": True, "tool_count": len(tools), "error": ""}
        except asyncio.TimeoutError:
            return {"ok": False, "tool_count": 0, "error": "连接超时（15s）"}
        except Exception as exc:
            return {"ok": False, "tool_count": 0, "error": str(exc)[:100]}

    tasks = [_test_one(name, cfg) for name, cfg in servers.items()]
    results_list = await asyncio.gather(*tasks)

    results = {}
    for name, result in zip(servers.keys(), results_list):
        results[name] = result

    return {"results": results}


# ==================== MCP 服务器 CRUD ====================

class McpServerCreate(BaseModel):
    """添加 MCP 服务器。"""
    name: str
    command: str = ""
    args: list[str] = []
    transport: str = "stdio"
    url: str = ""


class McpServerUpdate(BaseModel):
    """更新 MCP 服务器。"""
    command: str | None = None
    args: list[str] | None = None
    transport: str | None = None
    url: str | None = None


@router.post("/settings/mcp-servers")
def add_mcp_server(req: McpServerCreate) -> dict:
    """添加一个 MCP 服务器配置。"""
    name = req.name.strip()
    if not name:
        raise ValidationError("名称不能为空")
    if req.transport == "stdio" and not req.command:
        raise ValidationError("stdio 模式需要 command")

    settings = user_settings.load()
    mcp = settings.setdefault("mcp_servers", {})
    if name in mcp:
        raise ValidationError(f"MCP 服务器 '{name}' 已存在")

    mcp[name] = {
        "command": req.command,
        "args": req.args,
        "transport": req.transport,
    }
    if req.url:
        mcp[name]["url"] = req.url

    user_settings.save(settings)
    logger.info("MCP 服务器已添加: %s", name)
    return {"status": "ok", "name": name}


@router.put("/settings/mcp-servers/{name}")
def update_mcp_server(name: str, req: McpServerUpdate) -> dict:
    """更新 MCP 服务器配置。"""
    settings = user_settings.load()
    mcp = settings.get("mcp_servers", {})
    if name not in mcp:
        raise NotFoundError(f"MCP 服务器 '{name}' 不存在")

    if req.command is not None:
        mcp[name]["command"] = req.command
    if req.args is not None:
        mcp[name]["args"] = req.args
    if req.transport is not None:
        mcp[name]["transport"] = req.transport
    if req.url is not None:
        mcp[name]["url"] = req.url

    user_settings.save(settings)
    logger.info("MCP 服务器已更新: %s", name)
    return {"status": "ok"}


@router.delete("/settings/mcp-servers/{name}")
def delete_mcp_server(name: str) -> dict:
    """删除 MCP 服务器。"""
    settings = user_settings.load()
    mcp = settings.get("mcp_servers", {})
    if name not in mcp:
        raise NotFoundError(f"MCP 服务器 '{name}' 不存在")

    del mcp[name]
    user_settings.save(settings)
    logger.info("MCP 服务器已删除: %s", name)
    return {"status": "ok"}
