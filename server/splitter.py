"""文本分割模块。

将长文档切分为适合嵌入和检索的文本块。
支持按知识库类型选择不同策略：
1. 小说（novel）：按章节切分 + 长章节细切
2. 技术文档（tech）：按 Markdown 标题层级切分 + 递归细分
3. 项目文档（project）：保护代码块/表格的递归切分
4. 通用文档（general）：使用全局配置

小说章节样式兼容：
- 卷名 : 第X章 标题  （如 少女不死于童话镇 : 第一章 伊始之日）
- 卷名 : 终章/间章/序章 标题
- 第X章 标题
- 第X卷 卷名
- Chapter X Title / CHAPTER X
- X. 标题 / X、标题
- Vol.X Chapter Y
- 纯卷名行后接章节
"""

import re

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_core.documents import Document

from server.config import RAGConfig


# 中式/日式/数字章节号
_CHAPTER_NUM = r"[一二三四五六七八九十百千万零壹贰叁肆伍陆柒捌玖拾佰仟0-9\d]+"

# 常见章节标题正则（按优先级排序）
CHAPTER_PATTERNS = [
    # 卷名 : 第X章 标题
    re.compile(r"^\s*(.+?)\s*[:：]\s*(第\s*" + _CHAPTER_NUM + r"\s*[章回卷]|终章|间章|序章|卷末终章|外传)\s*(.*?)\s*$"),
    # 第X章 标题
    re.compile(r"^\s*(第\s*" + _CHAPTER_NUM + r"\s*[章回卷])\s*(.*?)\s*$"),
    # 序章 / 终章 / 间章 / 外传
    re.compile(r"^\s*(序章|终章|间章|外传|尾声|后记|前言|引言)\s*(.*?)\s*$"),
    # Chapter / CHAPTER / Ch.
    re.compile(r"^\s*(Chapter|CHAPTER|Ch\.)\s*(\d+)\s*(.*?)\s*$", re.IGNORECASE),
    # Vol.1 / 第一卷 / 卷一
    re.compile(r"^\s*(?:第\s*" + _CHAPTER_NUM + r"\s*卷|卷\s*" + _CHAPTER_NUM + r"|Vol\.?\s*\d+)\s*(.*?)\s*$"),
    # 1. 标题 / 1、标题 / 1 标题（仅当标题较像章节名时生效，长度限制在匹配器内处理）
    re.compile(r"^\s*(\d+)\s*[、.．]\s*(.+?)\s*$"),
]


def get_text_splitter(config: RAGConfig | None = None) -> RecursiveCharacterTextSplitter:
    """创建递归字符文本分割器。"""
    config = config or RAGConfig.from_json()
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )


# 明显不属于正文内容的章节标题，构建向量库时过滤掉
NOISE_CHAPTER_TITLES = {
    "作者 : 夜猫菌",
    "作者: 夜猫菌",
}
NOISE_KEYWORDS = ["图片 :", "图片:", "约稿证明", "书友群", "南锦外群", "新书已发", "完结感言"]


def _is_noise_chapter(title: str, content: str) -> bool:
    """判断章节是否为非正文噪声（如图片占位、作者公告）。"""
    if title in NOISE_CHAPTER_TITLES:
        return True
    for kw in NOISE_KEYWORDS:
        if kw in title or kw in content:
            return True
    return False


def _detect_chapter_pattern(text: str, sample_lines: int = 2000) -> re.Pattern | None:
    """自动检测文本中最可能的章节标题模式。

    从文本中采样若干行，依次用 CHAPTER_PATTERNS 匹配，选择能命中
    最多章节样式的模式；要求命中数 >= 3 且平均间隔合理。
    """
    lines = text.splitlines()[:sample_lines]
    best_pattern = None
    best_score = 0

    for pattern in CHAPTER_PATTERNS:
        hits: list[int] = []
        for idx, line in enumerate(lines):
            s = line.strip()
            if len(s) > 80:
                continue
            m = pattern.match(s)
            if not m:
                continue
            # 对数字序号模式做额外过滤，避免把普通列表行误判为章节
            if pattern.pattern.startswith(r"^\s*(\d+)\s*"):
                title = m.group(2).strip()
                # 要求标题含中文或英文单词，不能只是数字/符号
                if not re.search(r"[\u4e00-\u9fa5A-Za-z]", title):
                    continue
            hits.append(idx)

        if len(hits) < 3:
            continue

        # 间隔越均匀、总数越多，得分越高
        intervals = [hits[i + 1] - hits[i] for i in range(len(hits) - 1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        # 目标间隔 15 行左右（标题+空行+若干正文），间隔过大说明命中稀疏
        score = len(hits) * 100 - abs(avg_interval - 15) * 2
        if score > best_score:
            best_score = score
            best_pattern = pattern

    return best_pattern


def _match_chapter_title(line: str, pattern: re.Pattern) -> str | None:
    """用给定模式匹配章节标题，返回规范化标题或 None。"""
    s = line.strip()
    if len(s) > 80:
        return None
    m = pattern.match(s)
    if not m:
        return None

    groups = m.groups()
    # 按模式构造标题：优先保留卷/章结构
    if pattern.pattern.startswith(r"^\s*(.+?)\s*[:：]\s*"):
        # 卷名 : 章节 标题
        volume, chapter, title = groups[0], groups[1], groups[2] if len(groups) > 2 else ""
        chapter = chapter.strip()
        title = title.strip()
        if title:
            return f"{volume.strip()} : {chapter} {title}"
        return f"{volume.strip()} : {chapter}"

    if pattern.pattern.startswith(r"^\s*(第\s*"):
        # 第X章 标题
        chapter, title = groups[0], groups[1] if len(groups) > 1 else ""
        chapter = chapter.strip()
        title = title.strip()
        if title:
            return f"{chapter} {title}"
        return chapter

    if pattern.pattern.startswith(r"^\s*(序章|终章|间章"):
        chapter, title = groups[0], groups[1] if len(groups) > 1 else ""
        chapter = chapter.strip()
        title = title.strip()
        if title:
            return f"{chapter} {title}"
        return chapter

    if pattern.pattern.startswith(r"^\s*(Chapter|CHAPTER|Ch\.)"):
        chapter, title = f"第 {groups[1]} 章", groups[2] if len(groups) > 2 else ""
        title = title.strip()
        if title:
            return f"{chapter} {title}"
        return chapter

    if "Vol" in pattern.pattern or "卷" in pattern.pattern:
        volume, title = groups[0], groups[1] if len(groups) > 1 else ""
        volume = volume.strip()
        title = title.strip()
        if title:
            return f"{volume} {title}"
        return volume

    if pattern.pattern.startswith(r"^\s*(\d+)\s*"):
        num, title = groups[0], groups[1].strip()
        return f"第 {num} 章 {title}"

    return s


def _split_by_chapters(
    documents: list[Document],
    pattern: re.Pattern | None = None,
) -> list[Document]:
    """按章节标题把文档拆分为章节 Document 列表。

    每个章节的 metadata 会保留 source 和 chapter 标题。
    如果未提供 pattern，会自动检测文档中的章节样式。
    """
    chapters: list[Document] = []
    auto_pattern: re.Pattern | None = None

    for doc in documents:
        lines = doc.page_content.splitlines()
        current_title = "前言"
        current_lines: list[str] = []

        # 单文档内自动检测一次 pattern
        if pattern is None and auto_pattern is None:
            auto_pattern = _detect_chapter_pattern(doc.page_content)
        active_pattern = pattern or auto_pattern

        for line in lines:
            title: str | None = None
            if active_pattern is not None:
                title = _match_chapter_title(line, active_pattern)

            if title:
                # 保存上一个章节
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content and not _is_noise_chapter(current_title, content):
                        chapters.append(
                            Document(
                                page_content=content,
                                metadata={
                                    **doc.metadata,
                                    "chapter": current_title,
                                },
                            )
                        )
                current_title = title
                current_lines = []
            else:
                current_lines.append(line)

        # 保存最后一个章节
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content and not _is_noise_chapter(current_title, content):
                chapters.append(
                    Document(
                        page_content=content,
                        metadata={
                            **doc.metadata,
                            "chapter": current_title,
                        },
                    )
                )

    return chapters


def split_documents(documents: list[Document], config: RAGConfig | None = None) -> list[Document]:
    """将文档列表切分为文本块（使用全局配置）。"""
    config = config or RAGConfig.from_json()
    return split_documents_by_type(documents, "general", config)


def split_documents_by_type(
    documents: list[Document],
    kb_type: str = "general",
    config: RAGConfig | None = None,
) -> list[Document]:
    """按知识库类型切分文档。

    Args:
        documents: 原始文档列表。
        kb_type: 知识库类型，可选 novel/tech/project/general。
        config: RAG 配置，为空时自动读取 config.json。

    Returns:
        切分后的 Document 列表。
    """
    config = config or RAGConfig.from_json()

    if kb_type == "novel":
        return _split_novel_documents(documents, config)
    if kb_type == "tech":
        return _split_tech_documents(documents, config)
    if kb_type == "project":
        return _split_project_documents(documents, config)

    # general：使用全局配置
    if not config.chapter_split:
        splitter = get_text_splitter(config)
        return splitter.split_documents(documents)
    return _split_novel_documents(documents, config)


def _split_novel_documents(documents: list[Document], config: RAGConfig) -> list[Document]:
    """小说类型：按章节切分 + 长章节细切。

    会先自动检测章节标题样式；若检测失败（命中数<3），
    则回退到普通递归切分，避免把非章节行误判为章节。
    """
    threshold = config.chapter_chunk_threshold or 1500
    overlap = config.chapter_chunk_overlap or 200
    chapters = _split_by_chapters(documents)

    if not chapters:
        # 未识别到章节，回退到普通递归切分
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        return splitter.split_documents(documents)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=threshold,
        chunk_overlap=overlap,
        length_function=len,
        is_separator_regex=False,
    )

    final_chunks: list[Document] = []
    for chapter in chapters:
        chapter_title = chapter.metadata.get("chapter", "")
        if len(chapter.page_content) <= threshold:
            chapter.page_content = f"【{chapter_title}】\n{chapter.page_content}"
            final_chunks.append(chapter)
            continue

        sub_chunks = splitter.split_documents([chapter])
        for chunk in sub_chunks:
            chunk.page_content = f"【{chapter_title}】\n{chunk.page_content}"
            chunk.metadata["chapter"] = chapter_title
        final_chunks.extend(sub_chunks)

    return final_chunks


def _split_tech_documents(documents: list[Document], config: RAGConfig) -> list[Document]:
    """技术文档类型：按 Markdown 标题层级切分，超长部分再递归细分。"""
    chunk_size = 800
    chunk_overlap = 100
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )

    final_chunks: list[Document] = []
    for doc in documents:
        try:
            header_chunks = header_splitter.split_text(doc.page_content)
        except Exception:
            header_chunks = [doc]

        for chunk in header_chunks:
            chunk.metadata = {**doc.metadata, **chunk.metadata}
            if len(chunk.page_content) <= chunk_size:
                final_chunks.append(chunk)
                continue
            sub_chunks = fallback_splitter.split_documents([chunk])
            for sub in sub_chunks:
                sub.metadata = {**chunk.metadata, **sub.metadata}
            final_chunks.extend(sub_chunks)

    return final_chunks


def _split_project_documents(documents: list[Document], config: RAGConfig) -> list[Document]:
    """项目文档类型：保护代码块/表格的递归切分。"""
    chunk_size = 1000
    chunk_overlap = 150
    separators = ["\n## ", "\n### ", "\n#### ", "\n\n", "\n", "。", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        length_function=len,
        is_separator_regex=False,
    )
    return splitter.split_documents(documents)
