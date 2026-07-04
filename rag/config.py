"""RAG 配置模块。

从 config.json 读取模型、API Key 等配置，提供统一的配置访问入口。
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RAGConfig:
    """RAG 配置数据类。"""

    zhipu_api_key: str
    chat_model: str
    embedding_model: str
    chat_provider: str = "zhipuai"
    deepseek_api_key: str | None = None
    temperature: float = 0.5
    max_tokens: int | None = None
    timeout: int = 120
    streaming: bool = False
    enable_thinking: bool = True
    reasoning_effort: str | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    vector_store_dir: str = "./vectorstore"
    chunk_size: int = 500
    chunk_overlap: int = 50
    chapter_split: bool = False
    chapter_chunk_threshold: int = 1500
    chapter_chunk_overlap: int = 200
    top_k: int = 4
    enable_query_expansion: bool = False

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
