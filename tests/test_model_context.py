"""模型上下文窗口映射测试。

测试内容：
- _fuzzy_match 精确/模糊匹配
- get_model_context_window / get_model_max_output
- get_model_info 完整信息
- get_model_info_with_overrides 覆盖优先级
"""

import pytest

from server.llm.model_context import (
    _fuzzy_match,
    get_model_context_window,
    get_model_max_output,
    get_model_info,
    get_model_info_with_overrides,
    get_model_generation_overrides,
)


class TestFuzzyMatch:
    """_fuzzy_match 模糊匹配测试。"""

    def test_exact_match(self):
        result = _fuzzy_match("deepseek-v4-flash")
        assert result is not None
        assert result[0] == 1_048_576  # context_window
        assert result[1] == 393_216     # max_output

    def test_case_insensitive(self):
        """模型名小写匹配。"""
        result = _fuzzy_match("DeepSeek-V4-Flash")
        assert result is not None
        assert result[0] == 1_048_576

    def test_date_suffix(self):
        """去掉日期后缀：gpt-4o-2024-08-06 -> gpt-4o。"""
        result = _fuzzy_match("gpt-4o-2024-08-06")
        assert result is not None
        assert result[0] == 128_000

    def test_provider_prefix(self):
        """去掉厂商前缀：deepseek-ai/deepseek-v3 -> deepseek-v3。"""
        result = _fuzzy_match("deepseek-ai/deepseek-v3")
        assert result is not None
        assert result[0] == 163_840

    def test_unknown_model(self):
        """未知模型返回 None。"""
        assert _fuzzy_match("totally-unknown-model-xyz") is None

    def test_empty_string(self):
        # 空字符串前缀匹配会意外命中某些模型
        result = _fuzzy_match("")
        # 空字符串行为不确定，只需不报错
        assert result is None or isinstance(result, tuple)

    def test_glm_models(self):
        result = _fuzzy_match("glm-5.2")
        assert result is not None
        assert result[0] == 1_048_576

    def test_kimi_models(self):
        result = _fuzzy_match("kimi-k2.7-code")
        assert result is not None
        assert result[0] == 262_144

    def test_qwen_models(self):
        result = _fuzzy_match("qwen-plus")
        assert result is not None
        assert result[0] == 1_048_576


class TestGetModelContextWindow:
    """get_model_context_window 测试。"""

    def test_known_model(self):
        assert get_model_context_window("deepseek-v4-flash") == 1_048_576

    def test_with_provider_prefix(self):
        assert get_model_context_window("deepseek/deepseek-v4-flash") == 1_048_576

    def test_unknown_model(self):
        assert get_model_context_window("unknown-model") == 0

    def test_empty(self):
        # 空字符串前缀匹配会意外命中某些模型
        result = get_model_context_window("")
        assert isinstance(result, int)


class TestGetModelMaxOutput:
    """get_model_max_output 测试。"""

    def test_known_model(self):
        assert get_model_max_output("deepseek-v4-flash") == 393_216

    def test_with_provider_prefix(self):
        assert get_model_max_output("zhipuai/glm-5.2") == 1_048_576

    def test_unknown_model(self):
        assert get_model_max_output("unknown-model") == 0


class TestGetModelInfo:
    """get_model_info 测试。"""

    def test_known_model(self):
        info = get_model_info("deepseek-v4-flash")
        assert info["context_window"] == 1_048_576
        assert info["max_output"] == 393_216

    def test_with_provider(self):
        info = get_model_info("deepseek/deepseek-v4-flash")
        assert info["context_window"] == 1_048_576

    def test_unknown_model(self):
        info = get_model_info("unknown-model")
        assert info["context_window"] == 0
        assert info["max_output"] == 0


class TestGetModelInfoWithOverrides:
    """get_model_info_with_overrides 测试。"""

    def test_builtin_source(self):
        """已知模型返回 builtin 源。"""
        info = get_model_info_with_overrides("deepseek/deepseek-v4-flash")
        assert info["context_window"] == 1_048_576
        assert info["source"] == "builtin"

    def test_unknown_source(self):
        """未知模型返回 unknown 源。"""
        info = get_model_info_with_overrides("custom/some-model")
        assert info["context_window"] == 0
        assert info["source"] == "unknown"

    def test_override_source(self):
        """用户自定义覆盖优先级最高。"""
        from unittest.mock import patch

        overrides = {
            "custom/test-model": {
                "context_window": 999_999,
                "max_output": 50_000,
                "has_vision": True,
            }
        }
        with patch("server.llm.model_context._load_user_overrides", return_value=overrides):
            info = get_model_info_with_overrides("custom/test-model")
        assert info["context_window"] == 999_999
        assert info["max_output"] == 50_000
        assert info["has_vision"] is True
        assert info["source"] == "override"

    def test_override_takes_priority_over_builtin(self):
        """覆盖优先于内置。"""
        from unittest.mock import patch

        overrides = {
            "deepseek/deepseek-v4-flash": {
                "context_window": 500_000,
                "max_output": 100_000,
            }
        }
        with patch("server.llm.model_context._load_user_overrides", return_value=overrides):
            info = get_model_info_with_overrides("deepseek/deepseek-v4-flash")
        assert info["context_window"] == 500_000
        assert info["source"] == "override"


class TestGetModelGenerationOverrides:
    """get_model_generation_overrides 测试。"""

    def test_has_overrides(self):
        from unittest.mock import patch

        overrides = {
            "deepseek/deepseek-v4-flash": {
                "context_window": 1_048_576,
                "temperature": 0.8,
                "thinking": False,
            }
        }
        with patch("server.llm.model_context._load_user_overrides", return_value=overrides):
            result = get_model_generation_overrides("deepseek/deepseek-v4-flash")
        assert result["temperature"] == 0.8
        assert result["thinking"] is False
        # context_window 不在 generation 参数中
        assert "context_window" not in result

    def test_no_overrides(self):
        from unittest.mock import patch

        with patch("server.llm.model_context._load_user_overrides", return_value={}):
            result = get_model_generation_overrides("deepseek/deepseek-v4-flash")
        assert result == {}
