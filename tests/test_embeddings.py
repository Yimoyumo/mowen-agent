"""向量模型解析测试。

测试内容：
- _find_embedding_model 从模型列表中筛选 embedding 类模型
- resolve_embedding 多级解析（显式配置 > chat 厂商 > 遍历所有厂商）
- get_embeddings 自定义配置优先级
"""

import pytest

from server.core.config import RAGConfig
from server.llm.embeddings import _find_embedding_model, _EMBED_KEYWORDS, resolve_embedding


class TestFindEmbeddingModel:
    """_find_embedding_model 测试。"""

    def test_find_embedding_keyword(self):
        models = ["gpt-4o", "text-embedding-3-small", "dall-e"]
        result = _find_embedding_model(models)
        assert result == "text-embedding-3-small"

    def test_find_bge_keyword(self):
        models = ["llama-3", "bge-large-zh", "qwen-2"]
        result = _find_embedding_model(models)
        assert result == "bge-large-zh"

    def test_find_e5_keyword(self):
        models = ["e5-base-v2", "gpt-4o"]
        result = _find_embedding_model(models)
        assert result == "e5-base-v2"

    def test_find_gte_keyword(self):
        models = ["gte-base", "chat-model"]
        result = _find_embedding_model(models)
        assert result == "gte-base"

    def test_find_no_embedding_model(self):
        models = ["gpt-4o", "claude-3", "llama-3"]
        assert _find_embedding_model(models) is None

    def test_find_empty_list(self):
        assert _find_embedding_model([]) is None

    def test_embed_keywords_list(self):
        """关键词列表完整。"""
        assert "embedding" in _EMBED_KEYWORDS
        assert "bge-" in _EMBED_KEYWORDS
        assert "e5-" in _EMBED_KEYWORDS
        assert "gte-" in _EMBED_KEYWORDS


class TestResolveEmbedding:
    """resolve_embedding 多级解析测试。"""

    def _make_config(self, **kwargs) -> RAGConfig:
        defaults = dict(
            active_model="deepseek/deepseek-v4-flash",
            embedding_model="",
            providers={
                "deepseek": {"name": "DeepSeek", "api_key": "sk-123", "base_url": "https://api.deepseek.com/v1",
                             "models": ["deepseek-v4-flash", "deepseek-chat"]},
                "zhipuai": {"name": "智谱", "api_key": "sk-456", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                            "models": ["glm-4-flash", "embedding-3"]},
            },
        )
        defaults.update(kwargs)
        return RAGConfig(**defaults)

    def test_explicit_embedding_model(self):
        """1. 显式配置 embedding_model。"""
        cfg = self._make_config(embedding_model="zhipuai/embedding-3")
        provider, model, key = resolve_embedding(cfg)
        assert provider == "zhipuai"
        assert model == "embedding-3"
        assert key == "sk-456"

    def test_auto_from_chat_provider(self):
        """2. 从 chat 厂商模型列表中找 embedding。"""
        cfg = self._make_config(
            active_model="zhipuai/glm-4-flash",
            embedding_model="",
            providers={
                "zhipuai": {"api_key": "sk-456", "models": ["glm-4-flash", "embedding-3"]},
            }
        )
        provider, model, key = resolve_embedding(cfg)
        assert provider == "zhipuai"
        assert model == "embedding-3"
        assert key == "sk-456"

    def test_auto_traverse_all_providers(self):
        """3. chat 厂商没有 embedding，遍历所有厂商。"""
        cfg = self._make_config(
            active_model="deepseek/deepseek-v4-flash",
            embedding_model="",
            providers={
                "deepseek": {"api_key": "sk-123", "models": ["deepseek-v4-flash"]},
                "zhipuai": {"api_key": "sk-456", "models": ["glm-4-flash", "embedding-3"]},
            }
        )
        provider, model, key = resolve_embedding(cfg)
        assert provider == "zhipuai"
        assert model == "embedding-3"

    def test_no_embedding_found(self):
        """没有任何可用 embedding 模型时报错。"""
        cfg = self._make_config(
            embedding_model="",
            providers={
                "deepseek": {"api_key": "sk-123", "models": ["deepseek-v4-flash"]},
            }
        )
        with pytest.raises(ValueError, match="未找到可用的 Embedding 模型"):
            resolve_embedding(cfg)

    def test_no_api_key_skipped(self):
        """没有 API Key 的厂商被跳过。"""
        cfg = self._make_config(
            embedding_model="",
            providers={
                "deepseek": {"api_key": "", "models": ["deepseek-v4-flash"]},
                "zhipuai": {"api_key": "sk-456", "models": ["embedding-3"]},
            }
        )
        provider, _, _ = resolve_embedding(cfg)
        assert provider == "zhipuai"

    def test_explicit_model_no_key_fallback(self):
        """显式配置了 embedding_model 但对应厂商没有 key，从其他厂商兜底。"""
        cfg = self._make_config(
            embedding_model="custom/embed-x",
            providers={
                "custom": {"api_key": "", "models": ["embed-x"]},
                "zhipuai": {"api_key": "sk-456", "models": ["embedding-3"]},
            }
        )
        provider, model, key = resolve_embedding(cfg)
        # resolve_embedding 返回有 key 的厂商
        assert key == "sk-456"
        assert model in ("embed-x", "embedding-3")


class TestGetEmbeddingsCustom:
    """get_embeddings 自定义配置测试。"""

    def test_custom_config_takes_priority(self):
        """自定义配置启用时优先于厂商解析。"""
        from unittest.mock import patch, MagicMock

        cfg = RAGConfig(
            embedding_model="zhipuai/embedding-3",
            embedding_custom={
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-custom",
                "model": "text-embedding-3-small",
            },
            providers={"zhipuai": {"api_key": "sk-456", "models": ["embedding-3"]}},
        )

        with patch("server.llm.embeddings.OpenAIEmbeddings") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            from server.llm.embeddings import get_embeddings
            result = get_embeddings(cfg)
            assert result is mock_instance
            mock_cls.assert_called_once_with(
                api_key="sk-custom",
                model="text-embedding-3-small",
                base_url="https://api.example.com/v1",
            )

    def test_custom_disabled_falls_through(self):
        """自定义配置未启用时走正常厂商解析。"""
        from unittest.mock import patch, MagicMock

        cfg = RAGConfig(
            embedding_model="zhipuai/embedding-3",
            embedding_custom={"enabled": False, "base_url": "", "api_key": "", "model": ""},
            providers={"zhipuai": {"api_key": "sk-456", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                                    "models": ["embedding-3"]}},
        )

        with patch("server.llm.embeddings.ZhipuAIEmbeddings") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            from server.llm.embeddings import get_embeddings
            result = get_embeddings(cfg)
            assert result is mock_instance
            mock_cls.assert_called_once_with(api_key="sk-456", model="embedding-3")

    def test_custom_no_model_disabled(self):
        """自定义配置 enabled 但 model 为空时不生效。"""
        from unittest.mock import patch, MagicMock

        cfg = RAGConfig(
            embedding_model="zhipuai/embedding-3",
            embedding_custom={"enabled": True, "base_url": "", "api_key": "sk-custom", "model": ""},
            providers={"zhipuai": {"api_key": "sk-456", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                                    "models": ["embedding-3"]}},
        )

        with patch("server.llm.embeddings.ZhipuAIEmbeddings") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            from server.llm.embeddings import get_embeddings
            result = get_embeddings(cfg)
            assert result is mock_instance
