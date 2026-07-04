"""构建向量库脚本。

用法：
    python build_vectorstore.py
"""

from rag.pipeline import build_vector_store_from_directory


if __name__ == "__main__":
    # 默认从 data/ 目录加载所有 .txt 文件
    build_vector_store_from_directory("./data")
