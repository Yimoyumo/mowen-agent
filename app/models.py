"""Pydantic 数据模型定义。

所有 API 请求和响应的数据格式在此集中定义，
FastAPI 会自动完成类型校验和 JSON 序列化。
"""

from pydantic import BaseModel


# ==================== 请求模型 ====================

class ChatRequest(BaseModel):
    """通用对话请求。"""
    messages: list[dict]           # 对话历史 [{"role": "user"/"assistant", "content": "..."}]
    kb_id: str | None = None        # 知识库 ID，为空时纯对话，有值时启用 RAG 检索
    stream: bool = True             # 是否流式输出（False 时一次性返回完整回答）
    show_reasoning: bool = False    # 是否返回模型推理过程（DeepSeek reasoner 等模型支持）
    uploaded_files: list[dict] | None = None  # [{token, filename}] 用户上传的文件，Agent 导入沙盒
    session_id: str | None = None   # 会话 ID，用于沙盒跨消息持久化


class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求。"""
    name: str                       # 知识库名称（必填）
    description: str = ""           # 描述（可选）
    kb_type: str = "general"        # 类型：novel/tech/project/general


# ==================== 响应模型 ====================

class KnowledgeBaseResponse(BaseModel):
    """知识库列表/详情响应。"""
    id: str
    name: str
    description: str
    created_at: str                 # ISO 格式时间戳
    kb_type: str                    # novel/tech/project/general


class KnowledgeBaseDocumentInfo(BaseModel):
    """知识库内单个文档的统计信息。"""
    file_name: str                  # 文件名
    chunks: int                     # 切分后的文本块数
    chapters: list[str]             # 包含的章节列表


class KnowledgeBaseDocumentsResponse(BaseModel):
    """知识库文档列表响应（嵌套文档信息）。"""
    kb_id: str
    kb_name: str
    total_chunks: int               # 所有文档的文本块总数
    documents: list[KnowledgeBaseDocumentInfo]  # 按文件分组的文档信息


class ConfigResponse(BaseModel):
    """系统配置响应（只读）。"""
    chat_provider: str               # 对话模型厂商：deepseek / zhipuai
    chat_model: str                 # 对话模型名称
    embedding_model: str            # 向量模型名称
    top_k: int                      # 检索返回的文档数
    chunk_size: int                 # 文档切分块大小
    chunk_overlap: int              # 切分重叠字符数
    chapter_split: bool             # 是否按章节切分
    chapter_chunk_threshold: int     # 章节切分阈值
    chapter_chunk_overlap: int       # 章节切分重叠
    enable_query_expansion: bool    # 是否开启查询扩写
    context_window: int = 0         # 当前模型的上下文窗口大小（token）
    max_output: int = 0             # 当前模型的最大输出 token 数
    has_vision: bool = False        # 当前模型是否支持视觉（多模态）
    temperature: float = 0.5        # 生成温度
    max_tokens: int | None = None   # 最大输出 token 数（generation）
    thinking: bool = True           # 是否开启思考模式
    reasoning_effort: str | None = None  # 推理强度: low/medium/high


class ModelContextInfo(BaseModel):
    """模型上下文窗口信息。"""
    model: str                      # 模型 ref，如 "deepseek/deepseek-v4-flash"
    context_window: int             # 上下文窗口大小（token）
    max_output: int                 # 最大输出 token 数
