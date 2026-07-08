"""RAG config dataclass - loaded from user_settings."""

from dataclasses import dataclass, field


def _split_model_ref(ref: str) -> tuple[str, str]:
    if "/" in ref:
        a, b = ref.split("/", 1)
        return a, b
    return "", ref


@dataclass
class RAGConfig:
    active_model: str = ""
    embedding_model: str = ""
    providers: dict = field(default_factory=dict)
    temperature: float = 0.5
    max_tokens: int | None = None
    timeout: int = 120
    streaming: bool = False
    enable_thinking: bool = True
    reasoning_effort: str | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    vector_store_dir: str = "./vectorstore"
    chunk_size: int = 500
    chunk_overlap: int = 50
    chapter_split: bool = False
    chapter_chunk_threshold: int = 1500
    chapter_chunk_overlap: int = 200
    top_k: int = 4
    enable_query_expansion: bool = False
    max_context_tokens: int = 0
    tavily_api_key: str = ""
    mcp_servers: dict = field(default_factory=dict)
    skills: list = field(default_factory=list)
    logging: dict = field(default_factory=dict)
    deepseek_api_key: str = ""
    zhipu_api_key: str = ""

    @property
    def chat_provider(self) -> str:
        p, _ = _split_model_ref(self.active_model)
        return p

    @property
    def chat_model(self) -> str:
        _, m = _split_model_ref(self.active_model)
        return m

    @property
    def embedding_provider(self) -> str:
        if not self.embedding_model:
            return ""
        p, _ = _split_model_ref(self.embedding_model)
        return p

    def get_active_api_key(self) -> str:
        return self.providers.get(self.chat_provider, {}).get("api_key", "")

    def get_embedding_api_key(self) -> str | None:
        ep = self.embedding_provider
        if ep and ep in self.providers:
            k = self.providers[ep].get("api_key", "")
            if k:
                return k
        for fid in ("zhipuai", "deepseek"):
            if fid in self.providers:
                k = self.providers[fid].get("api_key", "")
                if k:
                    return k
        return None

    def get_provider_base_url(self, pid: str = "") -> str:
        return self.providers.get(pid or self.chat_provider, {}).get("base_url", "")

    def list_preset_providers(self) -> list[dict]:
        return [
            {"id": pid, **d}
            for pid, d in self.providers.items()
            if d.get("preset")
        ]

    def list_all_models(self) -> list[str]:
        r = []
        for pid, d in self.providers.items():
            for m in d.get("models", []):
                r.append(f"{pid}/{m}")
        return r

    def get_active_model_context_window(self) -> int:
        """获取当前选中模型的上下文窗口大小（token 数）。"""
        from server.model_context import get_model_context_window
        return get_model_context_window(self.active_model)

    def get_active_model_max_output(self) -> int:
        """获取当前选中模型的最大输出 token 数。"""
        from server.model_context import get_model_max_output
        return get_model_max_output(self.active_model)

    def get_active_model_info(self) -> dict:
        """获取当前选中模型的完整信息（支持用户自定义覆盖）。"""
        from server.model_context import get_model_info_with_overrides
        info = get_model_info_with_overrides(self.active_model)
        return {"context_window": info["context_window"], "max_output": info["max_output"], "has_vision": info.get("has_vision", False)}

    def has_active_model_vision(self) -> bool:
        """当前选中模型是否支持视觉（多模态）。"""
        from server.model_context import get_model_info_with_overrides
        return get_model_info_with_overrides(self.active_model).get("has_vision", False)

    @classmethod
    def from_settings(cls) -> "RAGConfig":
        from server.user_settings import build_config, user_settings
        return build_config(user_settings.load())
