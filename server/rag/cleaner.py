"""数据清洗模块。

在文档加载之后、分块之前对 Document 内容进行通用清洗，
提升检索召回片段的质量。

清洗步骤（所有文档类型通用）：
1. 统一换行符：CRLF / CR -> LF
2. 去除 BOM 和零宽字符
3. 合并连续空行（>2 个连续换行压缩为 2 个）
4. 去除行首尾多余空白（保留缩进结构）
5. 移除页眉页脚模式（PDF 常见的页码、重复水印行）
6. 修复 PDF 提取导致的断词（行尾连字符 + 换行）
7. 移除控制字符（保留换行和制表符）
8. 过滤目录页（大量「标题 ... 页码」格式的行）
9. 过滤噪声章节（图片占位、作者公告等）
10. 过滤过短的无效文档
"""

import re
import unicodedata

from langchain_core.documents import Document

from server.core.logging_config import get_logger

logger = get_logger(__name__)

# ==================== 噪声检测 ====================

# 明显不属于正文内容的章节标题
NOISE_CHAPTER_TITLES = {
    "作者 : 夜猫菌",
    "作者: 夜猫菌",
}

# 噪声关键词：图片占位、作者公告等
NOISE_KEYWORDS = ["图片 :", "图片:", "约稿证明", "书友群", "南锦外群", "新书已发", "完结感言"]


def is_noise_chapter(title: str, content: str) -> bool:
    """判断章节是否为非正文噪声（如图片占位、作者公告）。

    供 splitter 的 _split_by_chapters 调用，在分块时跳过噪声章节。
    """
    if title in NOISE_CHAPTER_TITLES:
        return True
    for kw in NOISE_KEYWORDS:
        if kw in title or kw in content:
            return True
    return False


# ==================== 文本清洗 ====================

# 零宽字符、BOM 等不可见字符
_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
    r"\u2060\ufeff\u00ad]"
)

# 控制字符（保留 \n \t \r）
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 连续 3+ 个换行 -> 2 个换行
_MULTI_NEWLINE = re.compile(r"\n{3,}")

# 连续 3+ 个空格（非行首缩进）-> 1 个空格
_MULTI_SPACE = re.compile(r"(?<=\S) {3,}")

# 行尾连字符断词修复：word-\nword -> wordword
# 仅当连字符前后都是字母时才合并，避免误伤列表项（如 "- item"）
_HYPHEN_BREAK = re.compile(r"([a-zA-Z])-\n([a-zA-Z])")

# 页码行：纯数字、或 "第 X 页"、或 "Page X"、或 "- X -"
_PAGE_NUM_LINE = re.compile(
    r"^(?:"
    r"\d{1,4}"                               # 纯数字
    r"|第\s*\d{1,4}\s*页"                     # 第 X 页
    r"|Page\s*\d{1,4}"                        # Page X
    r"|\-\s*\d{1,4}\s*\-"                     # - X -
    r")\s*$",
    re.IGNORECASE,
)

# 目录行模式：标题（含中文/英文/数字） + 点/空格分隔符 + 数字页码
_TOC_LINE_PATTERN = re.compile(
    r"[\u4e00-\u9fa5A-Za-z0-9].*[.．\s]{3,}\s*\d{1,4}\s*$"
)


def _clean_text(text: str) -> str:
    """对单段文本执行清洗，返回清洗后的文本。"""
    if not text:
        return text

    # 1. 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. 去除 BOM 和零宽字符
    text = _INVISIBLE_CHARS.sub("", text)

    # 3. 移除控制字符
    text = _CONTROL_CHARS.sub("", text)

    # 4. Unicode 标准化（NFKC：全角->半角等）
    text = unicodedata.normalize("NFKC", text)

    # 5. 修复 PDF 断词
    text = _HYPHEN_BREAK.sub(r"\1\2", text)

    # 6. 按行处理：去除页码行、行首尾多余空白
    lines = text.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()

        # 跳过纯页码行
        if _PAGE_NUM_LINE.match(stripped):
            continue

        # 行内多余空格压缩
        stripped = _MULTI_SPACE.sub(" ", stripped)

        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)

    # 7. 压缩连续空行
    text = _MULTI_NEWLINE.sub("\n\n", text)

    # 8. 去除首尾空白
    text = text.strip()

    return text


def _filter_toc_page(doc: Document) -> bool:
    """判断单个文档是否为目录页，返回 True 表示应过滤。

    目录页特征：大量「标题 ... 页码」格式的行、行短且规律。
    目录信息密度低，嵌入向量库会浪费 token 并干扰检索。
    """
    lines = doc.page_content.splitlines()
    if len(lines) < 3:
        return False

    toc_lines = 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if len(s) > 100:   # 目录行通常较短
            continue
        if _TOC_LINE_PATTERN.match(s):
            toc_lines += 1

    # 超过 40% 的行匹配目录模式 -> 视为目录页
    ratio = toc_lines / max(len(lines), 1)
    return ratio >= 0.4 and toc_lines >= 2


# 清洗后低于此字符数的文档视为无效，直接丢弃
_MIN_DOC_CHARS = 5


def clean_documents(documents: list[Document]) -> list[Document]:
    """对文档列表执行通用数据清洗。

    所有文档类型通用，在分块之前调用。
    清洗内容包括：统一换行、去零宽字符、合并空行、
    去页码行、修复断词、过滤目录页、过滤过短文档等。

    Args:
        documents: 原始文档列表。

    Returns:
        清洗后的 Document 列表（可能比输入少，过短/目录页会被丢弃）。
    """
    if not documents:
        return documents

    cleaned: list[Document] = []
    dropped_short = 0
    dropped_toc = 0
    total_before = 0
    total_after = 0

    for doc in documents:
        original = doc.page_content
        total_before += len(original)

        text = _clean_text(original)

        new_doc = Document(page_content=text, metadata=doc.metadata)

        # 过滤目录页
        if _filter_toc_page(new_doc):
            dropped_toc += 1
            total_after += len(text)
            continue

        if len(text) < _MIN_DOC_CHARS:
            dropped_short += 1
            total_after += len(text)
            continue

        total_after += len(text)
        cleaned.append(new_doc)

    ratio = (1 - total_after / total_before) * 100 if total_before > 0 else 0
    logger.info(
        "数据清洗: %d -> %d 个文档 (丢弃 %d 个过短, %d 个目录页, 内容压缩 %.1f%%)",
        len(documents),
        len(cleaned),
        dropped_short,
        dropped_toc,
        ratio,
    )
    return cleaned
