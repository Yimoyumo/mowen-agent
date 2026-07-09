"""文档加载模块。

支持加载 .txt、.md、.pdf、.docx、.doc、.json、.csv 等格式。
"""

from pathlib import Path

from langchain_community.document_loaders import (
    CSVLoader,
    JSONLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_core.documents import Document

from server.core.logging_config import get_logger

logger = get_logger(__name__)

# 文件扩展名 -> Loader 映射
_LOADER_MAP = {
    ".txt": TextLoader,
    ".md": TextLoader,
    ".pdf": PyPDFLoader,
    ".docx": UnstructuredWordDocumentLoader,
    ".doc": UnstructuredWordDocumentLoader,
    ".csv": CSVLoader,
    ".json": JSONLoader,
}


def load_documents(file_path: str | Path) -> list[Document]:
    """从文件路径加载文档。

    Args:
        file_path: 文件路径，支持 txt/md/pdf/docx/doc/csv/json。

    Returns:
        Document 列表。
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path.absolute()}")

    suffix = file_path.suffix.lower()
    loader_cls = _LOADER_MAP.get(suffix)
    if loader_cls is None:
        raise ValueError(f"不支持的文件类型: {suffix}，支持: {', '.join(sorted(_LOADER_MAP))}")

    # JSONLoader 需要指定 jq_schema
    if loader_cls == JSONLoader:
        loader = JSONLoader(str(file_path), jq_schema=".", text_content=False, encoding="utf-8")
    elif loader_cls == TextLoader:
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        loader = loader_cls(str(file_path))

    docs = loader.load()
    logger.info("加载 %s: %d 个文档", file_path.name, len(docs))
    return docs


def load_directory(dir_path: str | Path, glob: str = "**/*.txt") -> list[Document]:
    """递归加载目录下匹配 glob 的所有文件。

    Args:
        dir_path: 目录路径。
        glob: 文件匹配模式。

    Returns:
        Document 列表。
    """
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(f"目录不存在: {dir_path.absolute()}")

    documents: list[Document] = []
    for file_path in dir_path.glob(glob):
        try:
            documents.extend(load_documents(file_path))
        except Exception as e:
            logger.warning("跳过 %s: %s", file_path.name, e)
    return documents
