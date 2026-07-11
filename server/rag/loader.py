"""文档加载模块。

支持加载 .txt、.md、.pdf、.docx、.doc、.json、.csv 等格式。

图片处理策略：
- PDF/Word 中的图片会被提取到同名子目录，不参与 RAG 流程
- 仅文字内容进入向量库
"""

from pathlib import Path

from langchain_community.document_loaders import (
    CSVLoader,
    JSONLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_core.documents import Document

from server.core.logging_config import get_logger

logger = get_logger(__name__)

# 非 PDF/Word 文件扩展名 -> Loader 映射
_LOADER_MAP = {
    ".txt": TextLoader,
    ".md": TextLoader,
    ".csv": CSVLoader,
    ".json": JSONLoader,
}

# PDF 文字页面：正文至少这么多字符才认为是文字页
_PDF_MIN_TEXT_CHARS = 50


def _load_pdf_pymupdf(file_path: Path) -> list[Document]:
    """用 pymupdf 加载 PDF：提取全部文字合并为整书，跳过图片页。

    合并为单个 Document 避免跨页割裂，切分时按章节/段落自然边界切分。
    """
    import fitz  # pymupdf

    parts: list[str] = []
    text_pages = 0
    skipped_pages = 0

    with fitz.open(str(file_path)) as doc:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text").strip()

            if len(text) >= _PDF_MIN_TEXT_CHARS:
                parts.append(text)
                text_pages += 1
            else:
                skipped_pages += 1

    # 合并为整书一个 Document
    full_text = "\n\n".join(parts)
    docs = [Document(page_content=full_text, metadata={"source": str(file_path)})]

    logger.info(
        "加载 %s: %d 个文字页合并为 1 个文档 (跳过 %d 个图片/空白页)",
        file_path.name,
        text_pages,
        skipped_pages,
    )
    return docs


def _load_docx_text(file_path: Path) -> list[Document]:
    """加载 Word 文档：仅提取文字，跳过图片。"""
    loader = UnstructuredWordDocumentLoader(str(file_path))
    docs = loader.load()
    logger.info("加载 %s: %d 个文档 (图片已跳过)", file_path.name, len(docs))
    return docs


def load_documents(file_path: str | Path) -> list[Document]:
    """从文件路径加载文档。

    支持 txt/md/csv/json/PDF/Word。
    PDF/Word 中的图片直接跳过，仅文字进入 RAG。

    Args:
        file_path: 文件路径。

    Returns:
        Document 列表（仅文字内容）。
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path.absolute()}")

    suffix = file_path.suffix.lower()

    # PDF 用 pymupdf 提取文字 + 图片
    if suffix == ".pdf":
        return _load_pdf_pymupdf(file_path)

    # Word 用 UnstructuredLoader + zip 提取图片
    if suffix in (".docx", ".doc"):
        return _load_docx_text(file_path)

    # 其他格式
    loader_cls = _LOADER_MAP.get(suffix)
    if loader_cls is None:
        raise ValueError(
            f"不支持的文件类型: {suffix}，支持: {', '.join(sorted(_LOADER_MAP))}, .pdf, .docx, .doc"
        )

    if loader_cls == JSONLoader:
        loader = JSONLoader(str(file_path), jq_schema=".", text_content=False, encoding="utf-8")
    elif loader_cls == TextLoader:
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        loader = loader_cls(str(file_path))

    docs = loader.load()
    logger.info("加载 %s: %d 个文档", file_path.name, len(docs))
    return docs


def load_directory(dir_path: str | Path, glob: str = "**/*") -> list[Document]:
    """递归加载目录下匹配 glob 的所有文件。

    Args:
        dir_path: 目录路径。
        glob: 文件匹配模式（默认 **/* 加载所有文件）。

    Returns:
        Document 列表。
    """
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(f"目录不存在: {dir_path.absolute()}")

    # 支持的文件后缀
    allowed = {".txt", ".md", ".pdf", ".docx", ".doc", ".csv", ".json"}

    documents: list[Document] = []
    for file_path in dir_path.glob(glob):
        if file_path.suffix.lower() not in allowed:
            continue
        try:
            documents.extend(load_documents(file_path))
        except Exception as e:
            logger.warning("跳过 %s: %s", file_path.name, e)
    return documents
