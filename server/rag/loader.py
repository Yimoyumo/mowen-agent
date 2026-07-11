"""文档加载模块。

支持加载 .txt、.md、.pdf、.docx、.doc、.json、.csv 等格式。
PDF 使用 pymupdf 加载：优先提取文字，空白/扫描页渲染为图片（供多模态嵌入）。
"""

import base64
import io
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

# 非 PDF 文件扩展名 -> Loader 映射
_NON_PDF_LOADER_MAP = {
    ".txt": TextLoader,
    ".md": TextLoader,
    ".docx": UnstructuredWordDocumentLoader,
    ".doc": UnstructuredWordDocumentLoader,
    ".csv": CSVLoader,
    ".json": JSONLoader,
}

# PDF 文字页面：正文至少这么多字符才认为是文字页
_PDF_MIN_TEXT_CHARS = 50


def _load_pdf_pymupdf(file_path: Path) -> list[Document]:
    """用 pymupdf 加载 PDF：优先文字，空白/扫描页渲染为图片。"""
    import fitz  # pymupdf

    docs: list[Document] = []
    text_pages = 0
    image_pages = 0

    with fitz.open(str(file_path)) as doc:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            meta = {"source": str(file_path), "page": page_num}

            if len(text) >= _PDF_MIN_TEXT_CHARS:
                docs.append(Document(page_content=text, metadata=meta))
                text_pages += 1
                continue

            # 空白/扫描页 → 渲染为 JPEG 图片（比 PNG 小 5-10 倍）
            pix = page.get_pixmap(dpi=120)
            img_bytes = pix.tobytes("jpeg", jpg_quality=75)
            b64 = base64.b64encode(img_bytes).decode("ascii")
            data_uri = f"data:image/jpeg;base64,{b64}"

            # page_content 以 [IMAGE] 标记，embedding 层会识别并送入多模态模型
            docs.append(Document(page_content=f"[IMAGE]\n{data_uri}", metadata=meta))
            image_pages += 1

    logger.info(
        "加载 %s: %d 页 (文字=%d, 图片=%d)",
        file_path.name,
        text_pages + image_pages,
        text_pages,
        image_pages,
    )
    return docs


def load_documents(file_path: str | Path) -> list[Document]:
    """从文件路径加载文档。

    支持 txt/md/csv/json 和 PDF（pymupdf 文字+图片双模式）。
    注意：docx/doc 目前仅提取文字，不支持嵌入图片。

    Args:
        file_path: 文件路径。

    Returns:
        Document 列表。
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path.absolute()}")

    suffix = file_path.suffix.lower()

    # PDF 用 pymupdf 的文字/图片双模式
    if suffix == ".pdf":
        return _load_pdf_pymupdf(file_path)

    # 非 PDF
    loader_cls = _NON_PDF_LOADER_MAP.get(suffix)
    if loader_cls is None:
        raise ValueError(
            f"不支持的文件类型: {suffix}，支持: {', '.join(sorted(_NON_PDF_LOADER_MAP))}, .pdf"
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
