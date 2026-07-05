"""旧版 RAG 模块（保留兼容 /ask 接口）。

包含旧版 RAG 检索生成链和管道。
新代码请使用 server.agent 和 server.retrieval。
"""

from server.legacy.chain import get_rag_chain, get_rag_streaming_chain
from server.legacy.pipeline import ask, ask_stream
