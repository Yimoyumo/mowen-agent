"""RAGConfig 配置测试。

测试内容：
- _split_model_ref 模型引用解析
- RAGConfig 属性（chat_provider/chat_model/embedding_provider）
- get_active_api_key / get_embedding_api_key
- get_provider_base_url
- list_preset_providers / list_all_models
- build_config 从 settings dict 构造
"""

from server.core.config import RAGConfig, _split_model_ref
from server.core.user_settings import _DEFAULT_SETTINGS, build_config


class TestSplitModelRef:
    """_split_model_ref 测试。"""

    def test_normal_ref(self):
        assert _split_model_ref("deepseek/deepseek-v4-flash") == ("deepseek", "deepseek-v4-flash")

    def test_no_slash(self):
        assert _split_model_ref("gpt-4o") == ("", "gpt-4o")

    def test_multiple_slashes(self):
        # provider/model 的 model 部分可以含 /
        p, m = _split_model_ref("siliconflow/deepseek-ai/DeepSeek-V3")
        assert p == "siliconflow"
        assert m == "deepseek-ai/DeepSeek-V3"

    def test_empty_string(self):
        assert _split_model_ref("") == ("", "")

    def test_only_slash(self):
        assert _split_model_ref("/") == ("", "")


class TestRAGConfigProperties:
    """RAGConfig 属性测试。"""

    def _make_config(self, **kwargs) -> RAGConfig:
        defaults = dict(
            active_model="deepseek/deepseek-v4-flash",
            embedding_model="zhipuai/embedding-3",
            providers={
                "deepseek": {"name": "DeepSeek", "api_key": "sk-123", "base_url": "https://api.deepseek.com/v1"},
                "zhipuai": {"name": "智谱", "api_key": "sk-456", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
            },
        )
        defaults.update(kwargs)
        return RAGConfig(**defaults)

    def test_chat_provider(self):
        cfg = self._make_config()
        assert cfg.chat_provider == "deepseek"

    def test_chat_model(self):
        cfg = self._make_config()
        assert cfg.chat_model == "deepseek-v4-flash"

    def test_embedding_provider(self):
        cfg = self._make_config()
        assert cfg.embedding_provider == "zhipuai"

    def test_empty_embedding_model(self):
        cfg = self._make_config(embedding_model="")
        assert cfg.embedding_provider == ""

    def test_get_active_api_key(self):
        cfg = self._make_config()
        assert cfg.get_active_api_key() == "sk-123"

    def test_get_active_api_key_missing_provider(self):
        cfg = self._make_config(active_model="unknown/model")
        assert cfg.get_active_api_key() == ""

    def test_get_embedding_api_key_direct(self):
        cfg = self._make_config()
        assert cfg.get_embedding_api_key() == "sk-456"

    def test_get_embedding_api_key_fallback(self):
        """embedding provider 没有 key 时，从 zhipuai 兜底。"""
        cfg = self._make_config(
            embedding_model="custom/embed-x",
            providers={
                "custom": {"api_key": ""},
                "zhipuai": {"api_key": "sk-456"},
            },
        )
        assert cfg.get_embedding_api_key() == "sk-456"

    def test_get_provider_base_url(self):
        cfg = self._make_config()
        assert cfg.get_provider_base_url("deepseek") == "https://api.deepseek.com/v1"
        assert cfg.get_provider_base_url("zhipuai") == "https://open.bigmodel.cn/api/paas/v4"

    def test_get_provider_base_url_default(self):
        cfg = self._make_config()
        # 不传 pid 时用 chat_provider
        assert cfg.get_provider_base_url() == "https://api.deepseek.com/v1"

    def test_list_preset_providers(self):
        cfg = self._make_config(
            providers={
                "deepseek": {"name": "DeepSeek", "preset": True},
                "custom_abc": {"name": "Custom", "preset": False},
            }
        )
        presets = cfg.list_preset_providers()
        assert len(presets) == 1
        assert presets[0]["id"] == "deepseek"

    def test_list_all_models(self):
        cfg = self._make_config(
            providers={
                "deepseek": {"models": ["deepseek-v4-flash", "deepseek-chat"]},
                "zhipuai": {"models": ["glm-4-flash"]},
            }
        )
        all_models = cfg.list_all_models()
        assert "deepseek/deepseek-v4-flash" in all_models
        assert "deepseek/deepseek-chat" in all_models
        assert "zhipuai/glm-4-flash" in all_models
        assert len(all_models) == 3


class TestBuildConfig:
    """build_config 从 settings dict 构造 RAGConfig。"""

    def test_build_from_default(self):
        cfg = build_config(_DEFAULT_SETTINGS)
        assert isinstance(cfg, RAGConfig)
        assert cfg.active_model == _DEFAULT_SETTINGS["active_model"]
        assert cfg.chunk_size == _DEFAULT_SETTINGS["chunking"]["size"]
        assert cfg.top_k == _DEFAULT_SETTINGS["retrieval"]["top_k"]

    def test_build_with_custom_values(self):
        settings = {
            "active_model": "zhipuai/glm-4-flash",
            "embedding_model": "zhipuai/embedding-3",
            "providers": {"zhipuai": {"api_key": "sk-test"}},
            "generation": {"temperature": 0.8, "timeout": 60},
            "chunking": {"size": 800, "overlap": 100},
            "retrieval": {"top_k": 10, "query_expansion": True},
            "context": {"max_tokens": 4096},
            "agent": {"tavily_api_key": "tvly-xxx"},
            "vector_store": {"dir": "/tmp/vs"},
        }
        cfg = build_config(settings)
        assert cfg.chat_provider == "zhipuai"
        assert cfg.temperature == 0.8
        assert cfg.chunk_size == 800
        assert cfg.top_k == 10
        assert cfg.tavily_api_key == "tvly-xxx"
        assert cfg.vector_store_dir == "/tmp/vs"

    def test_build_empty_dict(self):
        """空 dict 不会崩，用默认值。"""
        cfg = build_config({})
        assert cfg.active_model == ""
        assert cfg.temperature == 0.5  # 默认值
        assert cfg.chunk_size == 500  # 默认值

    def test_build_with_embedding_custom(self):
        settings = {
            "embedding_custom": {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-custom",
                "model": "text-embedding-3-small",
            }
        }
        cfg = build_config(settings)
        assert cfg.embedding_custom["enabled"] is True
        assert cfg.embedding_custom["model"] == "text-embedding-3-small"
