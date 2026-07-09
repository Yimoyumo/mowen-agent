"""用户设置模块 — 唯一的配置文件。

data/user_settings.json 存储全部配置：
- 首次运行自动创建（含 6 个预设厂商 + 默认参数）
- 用户通过前端 UI 或手工编辑修改
- 所有模块统一通过 user_settings.load() 读取

active_model 格式: "provider/model"  如 "deepseek/deepseek-v4-flash"
embedding_model 格式: "provider/model"  如 "zhipuai/embedding-3"
"""

import json, os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from server.core.logging_config import get_logger
logger = get_logger(__name__)

_DATA_DIR = Path("data")
_SETTINGS_FILE = _DATA_DIR / "user_settings.json"

# ==================== 完整默认值（预设厂商 + 所有系统参数）====================

_DEFAULT_SETTINGS = {
    "active_model": "deepseek/deepseek-v4-flash",
    "embedding_model": "",
    "providers": {
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "desc": "DeepSeek V3/R1",
            "api_key": "",
            "models": ["deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
            "preset": True,
        },
        "zhipuai": {
            "name": "智谱 AI",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "desc": "GLM 系列",
            "api_key": "",
            "models": ["glm-4-flash", "glm-4-plus", "glm-4-flashx"],
            "preset": True,
        },
        "siliconflow": {
            "name": "硅基流动",
            "base_url": "https://api.siliconflow.cn/v1",
            "desc": "聚合开源模型",
            "api_key": "",
            "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen3-235B-A22B"],
            "preset": True,
        },
        "moonshot": {
            "name": "月之暗面 (Moonshot)",
            "base_url": "https://api.moonshot.cn/v1",
            "desc": "Kimi 系列",
            "api_key": "",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
            "preset": True,
        },
        "dashscope": {
            "name": "阿里百炼 (DashScope)",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "desc": "通义千问系列",
            "api_key": "",
            "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
            "preset": True,
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "desc": "GPT-4o / GPT-4.1",
            "api_key": "",
            "models": ["gpt-4.1", "gpt-4o", "gpt-4o-mini"],
            "preset": True,
        },
    },
    "generation": {
        "temperature": 0.5,
        "max_tokens": None,
        "timeout": 120,
        "thinking": True,
        "reasoning_effort": "high",
    },
    "chunking": {
        "size": 500,
        "overlap": 50,
        "chapter_split": True,
        "chapter_threshold": 1500,
        "chapter_overlap": 200,
    },
    "retrieval": {
        "top_k": 15,
        "query_expansion": True,
    },
    "context": {
        "max_tokens": 0,
    },
    "agent": {
        "tavily_api_key": "",
    },
    "mcp_servers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "transport": "stdio",
        },
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp", "--headless", "--browser", "chromium", "--output-dir", "downloads/playwright"],
            "transport": "stdio",
        },
    },
    "skills": ["data_analysis"],
    "logging": {
        "level": "INFO",
        "file": "logs/mowen.log",
        "max_bytes": 10485760,
        "backup_count": 5,
        "modules": {"server.agent": "DEBUG", "server.retrieval": "DEBUG"},
    },
    "vector_store": {
        "dir": "./vectorstore",
    },
    "embedding_custom": {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "model": "",
    },
    "persona": {"enabled": False, "content": ""},
    "user_profile": {"skills": "", "interests": "", "preferences": ""},
    "updated_at": None,
}


def _split_model_ref(ref: str) -> tuple[str, str]:
    if "/" in ref:
        a, b = ref.split("/", 1)
        return a, b
    return "", ref


# ==================== 便捷函数：从 settings dict 构造 RAGConfig ====================

def build_config(settings: dict):
    """从 settings dict 构造 RAGConfig 实例。"""
    from server.core.config import RAGConfig
    from server.llm.model_context import get_model_generation_overrides
    prov = deepcopy(settings.get("providers", {}))
    gen = settings.get("generation", {})
    chunk = settings.get("chunking", {})
    ret = settings.get("retrieval", {})
    ctx = settings.get("context", {})
    vs = settings.get("vector_store", {})
    agent = settings.get("agent", {})

    # 全局 generation 作为默认值，模型级覆盖优先
    active_model = settings.get("active_model", "")
    gen_override = get_model_generation_overrides(active_model)

    return RAGConfig(
        active_model=active_model,
        embedding_model=settings.get("embedding_model", ""),
        providers=prov,
        temperature=gen_override.get("temperature", gen.get("temperature", 0.5)),
        max_tokens=gen_override.get("max_tokens", gen.get("max_tokens")),
        timeout=gen.get("timeout", 120),
        enable_thinking=gen_override.get("thinking", gen.get("thinking", False)),
        reasoning_effort=gen_override.get("reasoning_effort", gen.get("reasoning_effort")),
        top_p=gen.get("top_p"),
        frequency_penalty=gen.get("frequency_penalty"),
        presence_penalty=gen.get("presence_penalty"),
        vector_store_dir=vs.get("dir", "./vectorstore"),
        embedding_custom=settings.get("embedding_custom", {}),
        chunk_size=chunk.get("size", 500),
        chunk_overlap=chunk.get("overlap", 50),
        chapter_split=chunk.get("chapter_split", False),
        chapter_chunk_threshold=chunk.get("chapter_threshold", 1500),
        chapter_chunk_overlap=chunk.get("chapter_overlap", 200),
        top_k=ret.get("top_k", 4),
        enable_query_expansion=ret.get("query_expansion", False),
        max_context_tokens=ctx.get("max_tokens", 0),
        tavily_api_key=agent.get("tavily_api_key", ""),
        mcp_servers=settings.get("mcp_servers", {}),
        skills=settings.get("skills", []),
        logging=settings.get("logging", {}),
        deepseek_api_key=prov.get("deepseek", {}).get("api_key", ""),
    )


class UserSettings:
    def __init__(self):
        self._cached_data: dict | None = None
        self._cached_mtime: float | None = None

    def load(self):
        """读取用户设置。使用 mtime 缓存，文件未变时直接返回缓存。"""
        # 检查文件 mtime 是否与缓存一致
        try:
            current_mtime = _SETTINGS_FILE.stat().st_mtime if _SETTINGS_FILE.exists() else 0
        except OSError:
            current_mtime = 0

        if self._cached_data is not None and current_mtime == self._cached_mtime:
            return self._cached_data

        import fcntl
        if not _SETTINGS_FILE.exists():
            data = deepcopy(_DEFAULT_SETTINGS)
            data.pop("updated_at", None)
            self.save(data)
            return self._merge(data)
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        lp = _SETTINGS_FILE.with_suffix(".lock")
        try:
            with open(lp, "w") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
                try:
                    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("read err: %s", e)
            return self._merge({})
        if "active_provider" in data and "active_model" not in data:
            data = self._migrate(data)

        merged = self._merge(data)
        self._cached_data = merged
        self._cached_mtime = current_mtime
        return merged

    def save(self, data):
        import fcntl
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        lp = _SETTINGS_FILE.with_suffix(".lock")
        tp = _SETTINGS_FILE.with_suffix(".tmp")
        data["updated_at"] = datetime.now().isoformat()
        with open(lp, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(tp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush(); os.fsync(f.fileno())
                os.replace(str(tp), str(_SETTINGS_FILE))
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        logger.info("settings saved")
        # 保存后刷新缓存（同时更新 mtime，避免重复读盘）
        self._cached_data = self._merge(deepcopy(data))
        try:
            self._cached_mtime = _SETTINGS_FILE.stat().st_mtime
        except OSError:
            self._cached_mtime = None

    def update(self, updates):
        cur = self.load(); merged = self._deep_merge(cur, updates)
        self.save(merged); return merged

    def reset(self):
        d = self._merge({}); self.save(d); return d

    def set_active_model(self, ref):
        s = self.load(); s["active_model"] = ref; self.save(s)

    def get_active_model(self):
        return self.load().get("active_model", "")

    def get_persona_prompt(self):
        s = self.load().get("persona", {})
        return s["content"].strip() if s.get("enabled") and s.get("content","").strip() else ""

    def get_profile_prompt(self):
        p = self.load().get("user_profile", {})
        lines = []
        for k, pre in [("skills","skills"),("interests","interests"),("preferences","preferences")]:
            if p.get(k,"").strip(): lines.append(f"user_{pre}: {p[k].strip()}")
        return "\n\n## user profile\n\n"+"\n".join(lines) if lines else ""

    def _migrate(self, old):
        logger.info("migrating old user_settings...")
        new = {}
        om = old.get("model",{})
        op = om.get("provider","") or old.get("active_provider","")
        oc = om.get("chat_model","")
        if op and oc: new["active_model"] = f"{op}/{oc}"
        elif op: new["active_model"] = op
        new["providers"] = old.get("providers", om.get("providers",{}))
        for k in ("retrieval","generation","persona","user_profile","updated_at"):
            if k in old: new[k] = old[k]
        self.save(new)
        return new

    def _merge(self, data):
        r = {}
        # 先处理默认值中的 key
        for k, dv in _DEFAULT_SETTINGS.items():
            if isinstance(dv, dict) and not k.startswith("_"):
                uv = data.get(k) if isinstance(data.get(k), dict) else {}
                r[k] = {**dv, **uv}
            elif isinstance(dv, list):
                r[k] = data.get(k, dv)
            else:
                r[k] = data.get(k, dv)
        # 再保留用户文件中不在默认值里的额外字段（如 model_context_overrides）
        for k, v in data.items():
            if k not in r and not k.startswith("_"):
                r[k] = v
        return r

    def _deep_merge(self, base, updates):
        for k, v in updates.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = self._deep_merge(base[k], v)
            else: base[k] = v
        return base

user_settings = UserSettings()
