"""用户配置管理测试。

测试内容：
- _DEFAULT_SETTINGS 默认配置完整性
- _merge 合并逻辑（默认值 + 用户覆盖 + 额外字段保留）
- _deep_merge 深层合并
- UserSettings 类的 load/save/update/reset/set_active_model
- build_config 从 settings 构造 RAGConfig
"""

import json
import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from server.core.user_settings import (
    _DEFAULT_SETTINGS,
    _split_model_ref,
    build_config,
    UserSettings,
)


class TestDefaultSettings:
    """_DEFAULT_SETTINGS 默认配置测试。"""

    def test_has_required_keys(self):
        required = [
            "active_model", "embedding_model", "providers", "generation",
            "chunking", "retrieval", "context", "agent", "mcp_servers",
            "skills", "logging", "vector_store", "embedding_custom",
            "persona", "user_profile",
        ]
        for key in required:
            assert key in _DEFAULT_SETTINGS, f"缺少默认配置项: {key}"

    def test_active_model_format(self):
        model = _DEFAULT_SETTINGS["active_model"]
        assert "/" in model, "active_model 必须为 provider/model 格式"

    def test_providers_has_preset(self):
        providers = _DEFAULT_SETTINGS["providers"]
        assert "deepseek" in providers
        assert providers["deepseek"].get("preset") is True

    def test_embedding_custom_defaults(self):
        ec = _DEFAULT_SETTINGS["embedding_custom"]
        assert ec["enabled"] is False
        assert ec["base_url"] == ""
        assert ec["api_key"] == ""
        assert ec["model"] == ""

    def test_generation_has_required_fields(self):
        gen = _DEFAULT_SETTINGS["generation"]
        assert "temperature" in gen
        assert "max_tokens" in gen

    def test_chunking_has_required_fields(self):
        chunk = _DEFAULT_SETTINGS["chunking"]
        for key in ["size", "overlap", "chapter_split", "chapter_threshold"]:
            assert key in chunk

    def test_retrieval_has_required_fields(self):
        ret = _DEFAULT_SETTINGS["retrieval"]
        assert "top_k" in ret
        assert "query_expansion" in ret


class TestSplitModelRef:
    """_split_model_ref 测试（user_settings 模块内的）。"""

    def test_normal(self):
        assert _split_model_ref("deepseek/chat") == ("deepseek", "chat")

    def test_no_slash(self):
        assert _split_model_ref("model") == ("", "model")

    def test_empty(self):
        assert _split_model_ref("") == ("", "")


class TestMerge:
    """UserSettings._merge 合并逻辑测试。"""

    def test_merge_empty(self):
        """空 dict 合并后全部用默认值。"""
        us = UserSettings()
        merged = us._merge({})
        assert merged["active_model"] == _DEFAULT_SETTINGS["active_model"]
        assert merged["chunking"]["size"] == _DEFAULT_SETTINGS["chunking"]["size"]

    def test_merge_user_override(self):
        """用户配置覆盖默认值。"""
        us = UserSettings()
        user_data = {"active_model": "custom/my-model"}
        merged = us._merge(user_data)
        assert merged["active_model"] == "custom/my-model"

    def test_merge_nested_dict(self):
        """嵌套 dict 深度合并。"""
        us = UserSettings()
        user_data = {"generation": {"temperature": 0.9}}
        merged = us._merge(user_data)
        assert merged["generation"]["temperature"] == 0.9
        # 其他字段保持默认
        assert merged["generation"]["max_tokens"] == _DEFAULT_SETTINGS["generation"]["max_tokens"]

    def test_merge_preserves_extra_keys(self):
        """不在默认值中的额外字段保留。"""
        us = UserSettings()
        user_data = {"model_context_overrides": {"custom/x": {"context_window": 999999}}}
        merged = us._merge(user_data)
        assert merged["model_context_overrides"] == {"custom/x": {"context_window": 999999}}

    def test_merge_providers_deep(self):
        """providers 嵌套合并。"""
        us = UserSettings()
        user_data = {
            "providers": {
                "deepseek": {"api_key": "sk-override"},
            }
        }
        merged = us._merge(user_data)
        # _merge 对 providers 做浅层合并：用户值替换默认值
        # deepseek 的 api_key 被覆盖
        assert merged["providers"]["deepseek"]["api_key"] == "sk-override"


class TestDeepMerge:
    """UserSettings._deep_merge 测试。"""

    def test_deep_merge_nested(self):
        us = UserSettings()
        base = {"a": {"b": 1, "c": 2}}
        updates = {"a": {"b": 10}}
        result = us._deep_merge(base, updates)
        assert result["a"]["b"] == 10
        assert result["a"]["c"] == 2

    def test_deep_merge_new_key(self):
        us = UserSettings()
        base = {"a": 1}
        updates = {"b": 2}
        result = us._deep_merge(base, updates)
        assert result["a"] == 1
        assert result["b"] == 2

    def test_deep_merge_override_non_dict(self):
        us = UserSettings()
        base = {"a": {"b": 1}}
        updates = {"a": "string"}
        result = us._deep_merge(base, updates)
        assert result["a"] == "string"


class TestUserSettingsLoadSave:
    """UserSettings load/save 完整流程测试。"""

    def test_save_and_load(self, tmp_path, monkeypatch):
        """保存后能正确读取。"""
        us = UserSettings()
        # 清除缓存
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        test_data = {"active_model": "deepseek/test-model"}
        us.save(test_data)

        # 清除缓存后重新加载
        us._cached_data = None
        loaded = us.load()
        assert loaded["active_model"] == "deepseek/test-model"

    def test_load_nonexistent_creates_default(self, tmp_path, monkeypatch):
        """文件不存在时自动创建默认配置。"""
        us = UserSettings()
        us._cached_data = None

        settings_file = tmp_path / "user_settings.json"
        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", settings_file)
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        loaded = us.load()
        assert settings_file.exists()
        assert loaded["active_model"] == _DEFAULT_SETTINGS["active_model"]

    def test_update_partial(self, tmp_path, monkeypatch):
        """update 部分更新。"""
        us = UserSettings()
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        us.save({"active_model": "deepseek/v4-flash"})
        us._cached_data = None
        us.update({"chunking": {"size": 800}})

        loaded = us.load()
        assert loaded["active_model"] == "deepseek/v4-flash"
        assert loaded["chunking"]["size"] == 800

    def test_set_active_model(self, tmp_path, monkeypatch):
        """set_active_model 正确设置。"""
        us = UserSettings()
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        us.save({"active_model": "deepseek/v4-flash"})
        us._cached_data = None
        us.set_active_model("zhipuai/glm-4-flash")

        assert us.get_active_model() == "zhipuai/glm-4-flash"

    def test_get_persona_prompt_disabled(self, tmp_path, monkeypatch):
        """persona 未启用时返回空。"""
        us = UserSettings()
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        us.save({"persona": {"enabled": False, "content": "猫娘"}})
        us._cached_data = None
        assert us.get_persona_prompt() == ""

    def test_get_persona_prompt_enabled(self, tmp_path, monkeypatch):
        """persona 启用且有内容时返回。"""
        us = UserSettings()
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        us.save({"persona": {"enabled": True, "content": "你是猫娘助手"}})
        us._cached_data = None
        result = us.get_persona_prompt()
        assert "猫娘" in result

    def test_reset(self, tmp_path, monkeypatch):
        """reset 恢复默认值。"""
        us = UserSettings()
        us._cached_data = None

        monkeypatch.setattr("server.core.user_settings._SETTINGS_FILE", tmp_path / "user_settings.json")
        monkeypatch.setattr("server.core.user_settings._DATA_DIR", tmp_path)

        # 先保存自定义值
        us.save({"active_model": "custom/model"})
        us._cached_data = None

        # 重置
        result = us.reset()
        assert result["active_model"] == _DEFAULT_SETTINGS["active_model"]
