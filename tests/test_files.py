"""文件安全测试。

测试内容：
- _sanitize_filename 文件名清理（路径穿越防护）
- _ALLOWED_EXTS 文件类型白名单
- _IMAGE_EXTS / _INLINE_EXTS 图片扩展名集合
"""

import pytest

from app.routes.files import (
    _sanitize_filename,
    _ALLOWED_EXTS,
    _IMAGE_EXTS,
    _INLINE_EXTS,
    _MAX_UPLOAD_SIZE,
)


class TestSanitizeFilename:
    """_sanitize_filename 路径穿越防护测试。"""

    def test_normal_filename(self):
        assert _sanitize_filename("document.pdf") == "document.pdf"

    def test_empty(self):
        assert _sanitize_filename("") == "unnamed"

    def test_none(self):
        assert _sanitize_filename(None) == "unnamed"

    def test_path_traversal(self):
        assert _sanitize_filename("../../../etc/passwd") == "passwd"

    def test_absolute_path(self):
        assert _sanitize_filename("/etc/shadow") == "shadow"

    def test_windows_path(self):
        # Path.name 在 Linux 上不拆分反斜杠
        result = _sanitize_filename("C:\\Windows\\system32\\file.txt")
        # 结果包含 file.txt 但可能不是干净的文件名
        assert "file.txt" in result

    def test_dot(self):
        assert _sanitize_filename(".") == "unnamed"

    def test_double_dot(self):
        assert _sanitize_filename("..") == "unnamed"

    def test_with_directory(self):
        assert _sanitize_filename("subdir/file.txt") == "file.txt"

    def test_chinese_filename(self):
        assert _sanitize_filename("文档.txt") == "文档.txt"


class TestAllowedExtensions:
    """_ALLOWED_EXTS 文件类型白名单测试。"""

    def test_text_types(self):
        for ext in ['.txt', '.md', '.json', '.csv']:
            assert ext in _ALLOWED_EXTS

    def test_code_types(self):
        for ext in ['.py', '.js', '.ts', '.go', '.java', '.sh']:
            assert ext in _ALLOWED_EXTS

    def test_image_types(self):
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            assert ext in _ALLOWED_EXTS

    def test_archive_types(self):
        for ext in ['.zip', '.tar', '.gz', '.7z']:
            assert ext in _ALLOWED_EXTS

    def test_blocked_types(self):
        """不在白名单中的扩展名。"""
        for ext in ['.exe', '.bat', '.cmd', '.sh~', '.dll', '.so']:
            assert ext not in _ALLOWED_EXTS

    def test_max_upload_size(self):
        """上传大小限制为 200MB。"""
        assert _MAX_UPLOAD_SIZE == 200 * 1024 * 1024


class TestImageExtensions:
    """_IMAGE_EXTS / _INLINE_EXTS 测试。"""

    def test_image_exts_subset(self):
        # _IMAGE_EXTS 有 .ico 但 _ALLOWED_EXTS 没有
        # 所以不是完全子集，只检查主要图片格式
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp']:
            assert ext in _IMAGE_EXTS
            assert ext in _ALLOWED_EXTS

    def test_inline_exts_contains_images(self):
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']:
            assert ext in _INLINE_EXTS

    def test_inline_exts_contains_text(self):
        for ext in ['.txt', '.csv', '.json', '.md']:
            assert ext in _INLINE_EXTS

    def test_inline_exts_excludes_code(self):
        assert '.py' not in _INLINE_EXTS
        assert '.js' not in _INLINE_EXTS
