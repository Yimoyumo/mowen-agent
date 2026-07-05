"""RAG 配置模块。

从 config.json 读取模型、API Key 等配置，提供统一的配置访问入口。
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RAGConfig:
    """RAG 配置数据类。

    所有字段都有默认值，可通过 config.json 覆盖。
    API Key 优先从 config.json 读取，其次从环境变量读取。
    """

    # ---- 模型配置 ----
    zhipu_api_key: str                          # 智谱 AI API Key（用于 Embedding 和 GLM 对话）
    chat_model: str                             # 对话模型名称
    embedding_model: str                        # 向量模型名称
    chat_provider: str = "zhipuai"              # 对话模型厂商：deepseek / zhipuai
    deepseek_api_key: str | None = None         # DeepSeek API Key

    # ---- 生成参数 ----
    temperature: float = 0.5                    # 生成温度（越高越随机）
    max_tokens: int | None = None              # 最大生成 token 数
    timeout: int = 120                          # 请求超时（秒）
    streaming: bool = False                    # 是否流式输出
    enable_thinking: bool = True               # 是否启用思考模式（DeepSeek）
    reasoning_effort: str | None = None        # 推理深度：low/medium/high
    top_p: float | None = None                 # 核采样概率
    frequency_penalty: float | None = None    # 频率惩罚
    presence_penalty: float | None = None      # 存在惩罚

    # ---- 向量库与切分配置 ----
    vector_store_dir: str = "./vectorstore"    # 向量库持久化目录
    chunk_size: int = 500                      # 文本块大小（字符数）
    chunk_overlap: int = 50                    # 块间重叠字符数
    chapter_split: bool = False               # 是否按章节切分
    chapter_chunk_threshold: int = 1500        # 章节切分阈值（超过则细切）
    chapter_chunk_overlap: int = 200            # 章节细切重叠

    # ---- 检索配置 ----
    top_k: int = 4                             # 检索返回的文档数
    enable_query_expansion: bool = False       # 是否开启查询扩写

    @classmethod
    def from_json(cls, path: str | Path = "config.json") -> "RAGConfig":
        """从 JSON 配置文件加载配置。"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path.absolute()}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            zhipu_api_key=data.get("zhipu_api_key", os.getenv("ZHIPUAI_API_KEY", "")),
            chat_model=data.get("chat_model", "glm-4.6v-flashx"),
            embedding_model=data.get("embedding_model", "embedding-3"),
            chat_provider=data.get("chat_provider", "zhipuai"),
            deepseek_api_key=data.get("deepseek_api_key", os.getenv("DEEPSEEK_API_KEY")),
            temperature=data.get("temperature", 0.5),
            max_tokens=data.get("max_tokens"),
            timeout=data.get("timeout", 120),
            streaming=data.get("streaming", False),
            enable_thinking=data.get("enable_thinking", False),
            reasoning_effort=data.get("reasoning_effort"),
            top_p=data.get("top_p"),
            frequency_penalty=data.get("frequency_penalty"),
            presence_penalty=data.get("presence_penalty"),
            vector_store_dir=data.get("vector_store_dir", "./vectorstore"),
            chunk_size=data.get("chunk_size", 500),
            chunk_overlap=data.get("chunk_overlap", 50),
            chapter_split=data.get("chapter_split", False),
            chapter_chunk_threshold=data.get("chapter_chunk_threshold", 1500),
            chapter_chunk_overlap=data.get("chapter_chunk_overlap", 200),
            top_k=data.get("top_k", 4),
            enable_query_expansion=data.get("enable_query_expansion", False),
        )
