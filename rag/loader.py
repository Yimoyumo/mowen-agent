"""文档加载模块。

支持加载 .txt、.md 和常见文本文件。
"""

from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document


def load_documents(file_path: str | Path) -> list[Document]:
    """从文件路径加载文档。

    Args:
        file_path: 文件路径，支持 txt / md / 等纯文本格式。

    Returns:
        Document 列表。
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path.absolute()}")

    loader = TextLoader(str(file_path), encoding="utf-8")
    return loader.load()


def load_directory(dir_path: str | Path, glob: str = "**/*.txt") -> list[Document]:
    """递归加载目录下匹配 glob 的所有文本文件。

    Args:
        dir_path: 目录路径。
        glob: 文件匹配模式，默认递归加载所有 .txt 文件。

    Returns:
        Document 列表。
    """
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(f"目录不存在: {dir_path.absolute()}")

    documents: list[Document] = []
    for file_path in dir_path.glob(glob):
        documents.extend(load_documents(file_path))
    return documents
