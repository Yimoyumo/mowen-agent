"""文档切分测试。

测试内容：
- _detect_chapter_pattern 章节模式检测
- _match_chapter_title 章节标题匹配
- _is_noise_chapter 噪声章节过滤
- _split_by_chapters 按章节切分
- split_documents_by_type 各类型切分（novel/tech/project/general）
- get_text_splitter 分割器创建
"""

import pytest
from langchain_core.documents import Document

from server.core.config import RAGConfig
from server.rag.splitter import (
    _detect_chapter_pattern,
    _match_chapter_title,
    _is_noise_chapter,
    _split_by_chapters,
    split_documents_by_type,
    get_text_splitter,
    CHAPTER_PATTERNS,
)


class TestDetectChapterPattern:
    """_detect_chapter_pattern 章节模式检测。"""

    def test_detect_chinese_chapters(self, sample_novel_text):
        pattern = _detect_chapter_pattern(sample_novel_text)
        assert pattern is not None

    def test_detect_no_pattern(self):
        """纯文本无章节标题时返回 None。"""
        text = "这是一段普通文本。\n" * 100
        pattern = _detect_chapter_pattern(text)
        assert pattern is None

    def test_detect_english_chapters(self):
        text = """Chapter 1 The Beginning

Some content here.

Chapter 2 The Middle

More content.

Chapter 3 The End

Final content.
"""
        pattern = _detect_chapter_pattern(text)
        assert pattern is not None

    def test_detect_numbered_chapters(self):
        text = """1. 第一章标题

内容内容

2. 第二章标题

更多内容

3. 第三章标题

最终内容
"""
        pattern = _detect_chapter_pattern(text)
        assert pattern is not None


class TestMatchChapterTitle:
    """_match_chapter_title 章节标题匹配。"""

    def test_match_chinese_chapter(self):
        pattern = _detect_chapter_pattern("第一章 伊始之日\n内容\n第二章 命运\n内容\n第三章 真相\n内容\n")
        assert pattern is not None
        title = _match_chapter_title("第一章 伊始之日", pattern)
        assert title is not None
        assert "第一章" in title
        assert "伊始之日" in title

    def test_match_long_line_skipped(self):
        """超过 80 字符的行不匹配。"""
        pattern = _detect_chapter_pattern("第一章 标题\n内容\n第二章 标题\n内容\n第三章 标题\n内容\n")
        long_line = "x" * 100
        title = _match_chapter_title(long_line, pattern)
        assert title is None

    def test_no_match(self):
        pattern = _detect_chapter_pattern("第一章 标题\n内容\n第二章 标题\n内容\n第三章 标题\n内容\n")
        title = _match_chapter_title("普通文本行", pattern)
        assert title is None


class TestIsNoiseChapter:
    """_is_noise_chapter 噪声过滤。"""

    def test_noise_title(self):
        assert _is_noise_chapter("作者 : 夜猫菌", "任何内容")

    def test_noise_keyword_in_content(self):
        assert _is_noise_chapter("某章节", "图片 : 某图片描述")

    def test_normal_chapter(self):
        assert not _is_noise_chapter("第一章 伊始之日", "清晨的阳光洒在小镇上")

    def test_noise_keyword_in_title(self):
        assert _is_noise_chapter("完结感言", "感谢大家支持")


class TestSplitByChapters:
    """_split_by_chapters 按章节切分。"""

    def test_split_novel(self, sample_novel_text):
        docs = [Document(page_content=sample_novel_text, metadata={"source": "test.txt"})]
        chapters = _split_by_chapters(docs)
        # 前言 + 第一章 + 第二章 + 第三章（终章可能合并到第三章）
        assert len(chapters) >= 3
        for ch in chapters:
            assert "chapter" in ch.metadata
            assert ch.page_content  # 非空

    def test_split_preserves_metadata(self, sample_novel_text):
        docs = [Document(page_content=sample_novel_text, metadata={"source": "novel.txt", "kb": "test"})]
        chapters = _split_by_chapters(docs)
        for ch in chapters:
            assert ch.metadata.get("source") == "novel.txt"

    def test_split_empty_document(self):
        docs = [Document(page_content="", metadata={})]
        chapters = _split_by_chapters(docs)
        assert len(chapters) == 0

    def test_split_no_chapters_detected(self):
        """无章节标题时全部作为前言。"""
        text = "这是第一段。\n这是第二段。\n这是第三段。"
        docs = [Document(page_content=text, metadata={})]
        chapters = _split_by_chapters(docs)
        # 无模式匹配，所有内容归入前言
        assert len(chapters) == 1
        assert chapters[0].metadata.get("chapter") == "前言"


class TestSplitDocumentsByType:
    """split_documents_by_type 各类型切分。"""

    def test_split_general(self):
        """通用类型：递归切分。"""
        docs = [Document(page_content="A" * 600, metadata={})]
        cfg = RAGConfig(chunk_size=200, chunk_overlap=20)
        chunks = split_documents_by_type(docs, "general", cfg)
        assert len(chunks) > 1

    def test_split_novel(self, sample_novel_text):
        """小说类型：按章节切分 + 长章节细切。"""
        docs = [Document(page_content=sample_novel_text, metadata={"source": "novel.txt"})]
        cfg = RAGConfig(chunk_size=500, chunk_overlap=50, chapter_split=True,
                        chapter_chunk_threshold=1500, chapter_chunk_overlap=200)
        chunks = split_documents_by_type(docs, "novel", cfg)
        assert len(chunks) >= 3
        for ch in chunks:
            # 每个块都应该有章节标记
            assert "【" in ch.page_content or "前言" in ch.page_content

    def test_split_tech(self, sample_markdown_text):
        """技术文档类型：按 Markdown 标题切分。"""
        docs = [Document(page_content=sample_markdown_text, metadata={"source": "guide.md"})]
        cfg = RAGConfig()
        chunks = split_documents_by_type(docs, "tech", cfg)
        assert len(chunks) > 1
        # 应该有 metadata 中的标题层级
        has_header = any("h1" in c.metadata or "h2" in c.metadata for c in chunks)
        assert has_header

    def test_split_project(self):
        """项目文档类型：保护代码块的递归切分。"""
        text = "# Title\n\n" + "代码内容 " * 200
        docs = [Document(page_content=text, metadata={})]
        cfg = RAGConfig()
        chunks = split_documents_by_type(docs, "project", cfg)
        assert len(chunks) >= 1

    def test_split_unknown_type_defaults_general(self):
        """未知类型回退到 general。"""
        docs = [Document(page_content="A" * 600, metadata={})]
        cfg = RAGConfig(chunk_size=200, chunk_overlap=20)
        chunks = split_documents_by_type(docs, "unknown_type", cfg)
        assert len(chunks) > 1


class TestGetTextSplitter:
    """get_text_splitter 测试。"""

    def test_create_splitter(self):
        cfg = RAGConfig(chunk_size=300, chunk_overlap=30)
        splitter = get_text_splitter(cfg)
        assert splitter is not None

    def test_split_text(self):
        cfg = RAGConfig(chunk_size=100, chunk_overlap=10)
        splitter = get_text_splitter(cfg)
        docs = [Document(page_content="A" * 250, metadata={})]
        chunks = splitter.split_documents(docs)
        assert len(chunks) > 1
