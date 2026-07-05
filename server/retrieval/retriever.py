"""多查询检索模块。

基于查询扩写结果，执行一次检索，并对特定类型的问题做后处理重排。
"""

import re

from langchain_core.documents import Document

from server.config import RAGConfig
from server.retrieval.query_expansion import expand_query
from server.vectorstore_chroma import load_vector_store


# 特殊查询类型：结局/最终类问题——避免扩写后语义发散，直接原问题检索
ENDING_QUESTION_KEYWORDS = ["结局", "最后", "最终", "完结", "终章", "结尾"]
ENDING_CHAPTER_KEYWORDS = ["终章", "结局", "完结", "卷末终章", "尾声"]

# 特殊查询类型：角色本质/身份类问题——优先召回揭示真相的章节
ESSENCE_QUESTION_KEYWORDS = ["什么样的存在", "本质", "真实身份", "真实面目", "到底是谁", "究竟是"]
ESSENCE_CHAPTER_KEYWORDS = ["恶意的神明", "终章", "卷末终章", "洛烟小姐的脚下埋着尸体"]


def _is_ending_question(question: str) -> bool:
    """判断问题是否在询问结局/最终内容。"""
    return any(kw in question for kw in ENDING_QUESTION_KEYWORDS)


def _is_essence_question(question: str) -> bool:
    """判断问题是否在询问某个角色的本质/真实身份。"""
    # 排除"什么关系"、"什么能力"等非本质类问题
    exclude_keywords = ["关系", "能力", "区别", "不同"]
    if any(kw in question for kw in exclude_keywords):
        return False
    return any(kw in question for kw in ESSENCE_QUESTION_KEYWORDS)


def _get_chapter_titles_by_keywords(vector_store, keywords: list[str]) -> set[str]:
    """从向量库中找出章节标题包含指定关键词的章节标题。"""
    all_data = vector_store._collection.get(include=["metadatas"])
    titles = set()
    for meta in all_data["metadatas"]:
        chapter = meta.get("chapter", "")
        if any(kw in chapter for kw in keywords):
            titles.add(chapter)
    return titles


def _retrieve_by_chapter_keywords(
    vector_store,
    question: str,
    config: RAGConfig,
    chapter_keywords: list[str],
) -> list[Document]:
    """从含指定关键词的章节中检索最相关的块。"""
    titles = _get_chapter_titles_by_keywords(vector_store, chapter_keywords)
    if not titles:
        return []

    try:
        docs = vector_store.similarity_search(
            question,
            k=config.top_k,
            filter={"chapter": {"$in": list(titles)}},
        )
        return docs
    except Exception as exc:
        print(f"章节过滤检索失败: {exc}")
        return []


def _merge_with_ending_priority(
    base_docs: list[Document],
    ending_docs: list[Document],
    top_k: int,
) -> list[Document]:
    """合并基础检索结果和结局章节检索结果，结局章节前置，去重。"""
    return _deduplicate_docs(ending_docs + base_docs, top_k)


def _deduplicate_docs(docs: list[Document], max_count: int) -> list[Document]:
    """按内容前缀去重，保留最相关的文档。"""
    seen = set()
    merged: list[Document] = []
    for doc in docs:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            merged.append(doc)
        if len(merged) >= max_count:
            break
    return merged


def _multi_query_retrieve(
    queries: list[str],
    retriever,
    top_k: int,
) -> list[Document]:
    """执行多查询检索，合并去重后返回 top_k 个文档。"""
    all_docs: list[Document] = []
    for query in queries:
        docs = retriever.invoke(query)
        all_docs.extend(docs)

    return _deduplicate_docs(all_docs, top_k)


def expand_and_retrieve(
    question: str,
    collection_name: str = "default",
    config: RAGConfig | None = None,
) -> list[Document]:
    """先扩写查询，再用扩写后的多个查询执行多查询检索。

    若扩写被禁用或失败（如 API 限流），则降级为直接使用原问题检索。
    检索完成后，对结局/最终类问题会做章节标题匹配的后处理重排。

    Args:
        question: 用户问题。
        collection_name: 目标知识库对应的 Chroma collection 名称。
        config: RAG 配置。

    Returns:
        检索到的相关文档列表，数量不超过 config.top_k。
    """
    config = config or RAGConfig.from_json()
    vector_store = load_vector_store(collection_name, config)
    retriever = vector_store.as_retriever(search_kwargs={"k": config.top_k})

    # 对结局/最终类问题，直接用原问题检索（避免扩写后语义发散），
    # 并额外从终章类章节中检索，合并后终章内容前置
    if _is_ending_question(question):
        print("检测到结局类问题，优先召回终章内容")
        base_docs = retriever.invoke(question)
        ending_docs = _retrieve_by_chapter_keywords(
            vector_store, question, config, ENDING_CHAPTER_KEYWORDS
        )
        return _merge_with_ending_priority(base_docs, ending_docs, config.top_k)

    # 对本质/真实身份类问题，优先召回揭示真相的章节
    if _is_essence_question(question):
        print("检测到本质/身份类问题，优先召回核心章节")
        base_docs = retriever.invoke(question)
        essence_docs = _retrieve_by_chapter_keywords(
            vector_store, question, config, ESSENCE_CHAPTER_KEYWORDS
        )
        return _merge_with_ending_priority(base_docs, essence_docs, config.top_k)

    if not config.enable_query_expansion:
        print("查询扩写已关闭，使用原问题检索")
        return retriever.invoke(question)

    # 查询扩写：用 LLM 生成多个语义相关的查询，提升召回率
    try:
        queries = expand_query(question, config)
        print(f"查询扩写完成，共 {len(queries)} 个查询: {queries}")
    except Exception as exc:
        # 扩写失败（如 API 限流），降级为原问题检索
        print(f"查询扩写失败，使用原问题检索: {exc}")
        queries = [question]

    # 多查询检索：对每个查询执行检索，合并去重
    return _multi_query_retrieve(queries, retriever, config.top_k)


def get_retriever(collection_name: str = "default", config: RAGConfig | None = None):
    """返回基础检索器（兼容旧接口）。"""
    config = config or RAGConfig.from_json()
    vector_store = load_vector_store(collection_name, config)
    return vector_store.as_retriever(search_kwargs={"k": config.top_k})
