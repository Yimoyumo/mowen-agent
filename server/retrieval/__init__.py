"""检索模块。

提供文档检索的核心能力：
- expand_and_retrieve: 查询扩写 + 多查询检索
- get_retriever: 基础检索器
- expand_query: 查询扩写
"""

from server.retrieval.retriever import expand_and_retrieve, get_retriever
from server.retrieval.query_expansion import expand_query

__all__ = ["expand_and_retrieve", "get_retriever", "expand_query"]
