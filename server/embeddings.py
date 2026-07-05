"""嵌入模型模块。

封装智谱 AI Embedding 接口，供向量库使用。
"""

from langchain_community.embeddings import ZhipuAIEmbeddings

from server.config import RAGConfig


def get_embeddings(config: RAGConfig | None = None) -> ZhipuAIEmbeddings:
    """获取智谱 AI 嵌入模型实例。"""
    config = config or RAGConfig.from_json()
    return ZhipuAIEmbeddings(
        api_key=config.zhipu_api_key,
        model=config.embedding_model,
    )
