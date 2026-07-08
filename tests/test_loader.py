"""文档加载测试。

测试内容：
- load_documents 从文件加载
- load_directory 从目录加载
- 文件不存在异常
"""

import pytest
from langchain_core.documents import Document

from server.rag.loader import load_documents, load_directory


class TestLoadDocuments:
    """load_documents 测试。"""

    def test_load_txt_file(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello World\nLine 2", encoding="utf-8")
        docs = load_documents(file_path)
        assert len(docs) == 1
        assert isinstance(docs[0], Document)
        assert "Hello World" in docs[0].page_content

    def test_load_md_file(self, tmp_path):
        file_path = tmp_path / "test.md"
        file_path.write_text("# Title\n\nContent", encoding="utf-8")
        docs = load_documents(file_path)
        assert len(docs) == 1
        assert "# Title" in docs[0].page_content

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_documents("/nonexistent/path/file.txt")

    def test_load_chinese_content(self, tmp_path):
        file_path = tmp_path / "chinese.txt"
        file_path.write_text("你好世界\n这是测试文本", encoding="utf-8")
        docs = load_documents(file_path)
        assert "你好世界" in docs[0].page_content

    def test_load_preserves_metadata(self, tmp_path):
        file_path = tmp_path / "meta.txt"
        file_path.write_text("content", encoding="utf-8")
        docs = load_documents(file_path)
        assert docs[0].metadata.get("source") is not None


class TestLoadDirectory:
    """load_directory 测试。"""

    def test_load_multiple_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("File A", encoding="utf-8")
        (tmp_path / "b.txt").write_text("File B", encoding="utf-8")
        docs = load_directory(tmp_path)
        assert len(docs) == 2

    def test_load_with_glob(self, tmp_path):
        (tmp_path / "a.txt").write_text("TXT file", encoding="utf-8")
        (tmp_path / "b.md").write_text("MD file", encoding="utf-8")
        docs = load_directory(tmp_path, glob="*.txt")
        assert len(docs) == 1

    def test_load_nonexistent_dir(self):
        with pytest.raises(FileNotFoundError):
            load_directory("/nonexistent/dir/")

    def test_load_empty_dir(self, tmp_path):
        docs = load_directory(tmp_path)
        assert len(docs) == 0

    def test_load_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_text("Root", encoding="utf-8")
        (sub / "b.txt").write_text("Sub", encoding="utf-8")
        docs = load_directory(tmp_path)
        assert len(docs) == 2
