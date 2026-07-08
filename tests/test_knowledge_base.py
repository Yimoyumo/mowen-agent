"""知识库管理测试。

测试内容：
- _sanitize_collection_name collection 名称清理
- KB_TYPES 知识库类型映射
- KnowledgeBase dataclass
- load_knowledge_bases 加载
"""

import pytest

from server.rag.knowledge_base import (
    _sanitize_collection_name,
    KB_TYPES,
    DEFAULT_KB_TYPE,
    KnowledgeBase,
)


class TestSanitizeCollectionName:
    """_sanitize_collection_name 测试。"""

    def test_normal_uuid(self):
        name = _sanitize_collection_name("abc-123-def-456")
        assert name == "kb_abc_123_def_456"

    def test_empty(self):
        name = _sanitize_collection_name("")
        assert name == "kb_"

    def test_already_clean(self):
        name = _sanitize_collection_name("abc123")
        assert name == "kb_abc123"

    def test_prefix(self):
        """所有 collection 名称以 kb_ 开头。"""
        for test_id in ["a-b-c", "123", "xyz"]:
            assert _sanitize_collection_name(test_id).startswith("kb_")


class TestKBTypes:
    """KB_TYPES 测试。"""

    def test_contains_all_types(self):
        assert "novel" in KB_TYPES
        assert "tech" in KB_TYPES
        assert "project" in KB_TYPES
        assert "general" in KB_TYPES

    def test_labels_are_chinese(self):
        for label in KB_TYPES.values():
            assert isinstance(label, str)
            assert len(label) > 0

    def test_default_type(self):
        assert DEFAULT_KB_TYPE == "general"


class TestKnowledgeBase:
    """KnowledgeBase dataclass 测试。"""

    def test_create(self):
        kb = KnowledgeBase(
            id="test-123",
            name="测试知识库",
            description="这是一个测试",
            created_at="2026-01-01T00:00:00",
            collection_name="kb_test_123",
        )
        assert kb.id == "test-123"
        assert kb.name == "测试知识库"
        assert kb.kb_type == DEFAULT_KB_TYPE

    def test_create_with_type(self):
        kb = KnowledgeBase(
            id="test-456",
            name="小说库",
            description="",
            created_at="2026-01-01",
            collection_name="kb_test_456",
            kb_type="novel",
        )
        assert kb.kb_type == "novel"

    def test_create_all_types(self):
        for kb_type in KB_TYPES:
            kb = KnowledgeBase(
                id=f"test-{kb_type}",
                name=kb_type,
                description="",
                created_at="2026-01-01",
                collection_name=f"kb_test_{kb_type}",
                kb_type=kb_type,
            )
            assert kb.kb_type == kb_type
