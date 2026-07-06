# 墨问 - AI Agent 助手

> 基于 LangGraph + DeepSeek 的智能 Agent，支持知识库检索、联网搜索、Docker 沙盒代码执行与流式对话。

## 功能

- **Agent 自主决策**：LLM 自动判断是否需要调用工具（知识库检索 / 联网搜索 / 沙盒执行）
- **Docker 沙盒**：在隔离的 Linux 容器中执行代码、安装包、处理文件，支持文件上传/下载
- **知识库 RAG**：上传文档后自动切分入库，回答时精准定位相关内容
- **联网搜索**：通过 Tavily 实时搜索最新信息（需配置 API Key）
- **网页抓取**：抓取指定 URL 的网页内容并转为 Markdown
- **MCP 工具集成**：通过 Model Context Protocol 连接外部工具服务器
- **Skills 技能系统**：Markdown 格式的可扩展场景指导，Agent 按需参考
- **流式输出**：逐 token 输出，支持展示推理过程（DeepSeek 思考链）
- **工具调用可视化**：前端实时显示工具调用状态和结果
- **知识库管理**：创建、上传文档、重建向量库、删除，按类型（小说/技术/项目/通用）定制回答策略
- **Markdown 渲染**：代码块、表格、列表、图片等完整支持
- **会话持久化**：localStorage 保存对话历史和运行时设置

## 架构

```
用户消息
  │
  ▼
┌──────────────────────────────────────────┐
│  LangGraph Agent (ReAct)                 │
│                                          │
│  ┌────────┐      ┌──────────────────┐    │
│  │  LLM   │◄────►│ Tool Executor   │    │
│  │ 思考   │      │                  │    │
│  │ 决策   │      │ 📚 知识库检索     │    │
│  │ 回答   │      │ 🌐 联网搜索      │    │
│  └────────┘      │ 📄 网页抓取       │    │
│      │           │ 🐳 Docker 沙盒   │    │
│      │           │ 🔧 MCP 外部工具  │    │
│      ▼           └──────────────────┘    │
│   流式输出 (SSE)                          │
│   token + tool_start/tool_end 事件       │
└──────────────────────────────────────────┘
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| Agent 框架 | LangGraph (ReAct) + create_react_agent |
| LLM | DeepSeek / 智谱 AI（可切换，注册表模式） |
| Embedding | 智谱 AI embedding-3 |
| 向量库 | Chroma |
| 沙盒 | Docker SDK for Python（mowen-sandbox 自建镜像） |
| MCP | langchain-mcp-adapters |
| API | FastAPI + SSE 流式 |
| 日志 | logging + RotatingFileHandler + 请求追踪 |
| 错误处理 | 统一异常体系 + 全局异常处理器 |

## 快速开始

### 后端

```sh
# 安装依赖
uv sync

# 启动 API 服务
uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```sh
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173

## 项目结构

```
.
├── api.py                  # 启动入口
├── data/user_settings.json # 用户配置（首次运行自动生成）
├── pyproject.toml          # 依赖管理
│
├── server/                 # 核心引擎包
│   ├── __init__.py             公共 API
│   ├── config.py               RAGConfig 配置（从 user_settings 加载）
│   ├── logging_config.py       日志模块（Logger 工厂 + 请求追踪）
│   ├── llm.py                  LLM 厂商工厂（注册表模式）
│   ├── embeddings.py           Embedding 模型
│   ├── splitter.py             文档切分
│   ├── loader.py               文档加载
│   ├── knowledge_base.py       知识库元数据管理（原子写入 + 文件锁）
│   ├── vectorstore_chroma.py   Chroma 向量库
│   ├── chain.py                RAG 链工具函数
│   ├── chat_chain.py           兼容层（重导出 agent.chat_stream）
│   ├── prompts/                提示词统一管理
│   │   ├── agent.py                Agent 系统提示词（段落组合）
│   │   ├── rag.py                  RAG 问答提示词
│   │   └── query_expansion.py      查询扩写提示词
│   ├── retrieval/              检索子包
│   │   ├── retriever.py            多查询检索
│   │   └── query_expansion.py      查询扩写
│   ├── agent/                  Agent 子包
│   │   ├── graph.py                LangGraph ReAct Agent
│   │   ├── tools.py                8 个工具（搜索/沙盒/网页抓取）
│   │   ├── sandbox.py               Docker 沙盒管理器
│   │   ├── mcp.py                   MCP 客户端（逐服务器容错）
│   │   └── skills.py                Skills 技能加载器
│   └── legacy/                 旧版兼容（/ask 接口）
│       ├── chain.py
│       └── pipeline.py
│
├── app/                    # FastAPI 路由层
│   ├── main.py                FastAPI 实例 + 中间件 + 生命周期
│   ├── errors.py              统一异常体系
│   ├── cleanup.py             文件清理（uploads/downloads 过期）
│   ├── models.py              Pydantic 数据模型
│   └── routes/                路由
│       ├── chat.py                对话接口（/chat/stream）
│       ├── config.py              配置与健康检查
│       ├── files.py               文件上传/下载（大小限制+类型白名单）
│       └── knowledge_bases.py     知识库 CRUD
│
├── skills/                 # 技能文件（Markdown）
│   ├── data_analysis.md         数据分析工作流程
│   └── web_scraping.md          网页爬取工作流程
│
├── Dockerfile.sandbox       # 沙盒 Docker 镜像定义
│
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── api/                API 调用
│       ├── components/         组件（chat / home / layout）
│       ├── composables/        组合式函数（useChat / useConfig）
│       ├── stores/             Pinia 状态管理
│       ├── types/              类型定义
│       └── views/              页面
│
├── data/                   # 文档上传目录
├── logs/                   # 日志文件（自动创建）
├── notebook/               # 学习笔记（Jupyter）
└── vectorstore/            # Chroma 持久化数据
```

## 配置

`data/user_settings.json` 是唯一配置文件，首次运行时自动生成默认配置。包含厂商管理、模型选择、生成参数、检索参数等：

```json
{
  "active_model": "deepseek/deepseek-v4-flash",
  "embedding_model": "zhipuai/embedding-3",
  "providers": {
    "deepseek": {
      "name": "DeepSeek",
      "preset": true,
      "api_key": "",
      "base_url": "https://api.deepseek.com/v1",
      "models": ["deepseek-v4-flash", "deepseek-v4-pro"]
    }
  },
  "generation": {
    "temperature": 0.5,
    "max_tokens": null,
    "streaming": false,
    "thinking": true
  },
  "chunking": {
    "size": 500,
    "overlap": 50,
    "chapter_split": false,
    "chapter_chunk_threshold": 1500,
    "chapter_chunk_overlap": 200
  },
  "retrieval": {
    "top_k": 15,
    "query_expansion": true
  },
  "context": {
    "max_tokens": 0
  },
  "agent": {
    "tavily_api_key": ""
  },
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "transport": "stdio"
    }
  },
  "skills": ["data_analysis"],
  "logging": {
    "level": "INFO",
    "file": "logs/mowen.log",
    "max_bytes": 10485760,
    "backup_count": 5,
    "modules": {
      "server.agent": "DEBUG",
      "server.retrieval": "DEBUG"
    }
  },
  "vector_store": {
    "dir": "./vectorstore"
  }
}
```

| 分组 | 说明 |
|------|------|
| `active_model` | 当前选中的模型，格式 `provider/model` |
| `embedding_model` | Embedding 模型，格式 `provider/model` |
| `providers` | 厂商配置：API Key、base_url、模型列表 |
| `generation` | 生成参数：temperature、max_tokens、thinking 等 |
| `chunking` | 文档切分：块大小、重叠、章节切分 |
| `retrieval` | 检索参数：top_k、查询扩写 |
| `context` | 上下文窗口限制（0 = 不限制） |
| `agent` | Agent 工具配置：tavily_api_key 启用联网搜索 |
| `mcp_servers` | 外部 MCP 服务器配置（逐服务器容错） |
| `skills` | 启用的技能列表，对应 skills/*.md 文件 |
| `logging` | 日志级别、文件路径、按模块独立级别 |
| `vector_store` | Chroma 持久化目录 |
| `persona` | 人格设定文本 |
| `user_profile` | 用户画像文本 |

## Agent 模式

Agent 自主决定何时调用工具，无需手动切换模式：

```
用户: "这个小说里最后谁赢了？"
Agent: → search_knowledge_base("最终结局") → 找到终章内容 → 回答

用户: "今天天气怎么样？"
Agent: → search_web("北京天气") → 返回实时天气

用户: "帮我画个柱状图"
Agent: → sandbox_write_file("plot.py") → sandbox_run("python plot.py")
      → sandbox_export_file("chart.png") → 图片直接在聊天中渲染

用户: "你好，介绍一下自己"
Agent: → 不调用工具，直接回答
```

### Agent 工具

| 工具 | 说明 |
|------|------|
| `sandbox_run` | 在 Docker 沙盒中执行 shell 命令 |
| `sandbox_write_file` | 在沙盒中创建/覆盖文件 |
| `sandbox_read_file` | 读取沙盒中的文件 |
| `sandbox_list_files` | 列出沙盒目录 |
| `sandbox_export_file` | 导出沙盒文件为下载链接（图片直接渲染） |
| `search_knowledge_base` | 搜索用户上传的知识库 |
| `search_web` | 联网搜索实时信息（Tavily） |
| `fetch_webpage` | 抓取指定网址的网页内容 |

### 提示词管理

所有提示词统一在 `server/prompts/` 包中管理：

| 文件 | 内容 | 类型 |
|------|------|------|
| `agent.py` | Agent 系统提示词（8 静态段落 + 3 动态段落） | PromptTemplate |
| `rag.py` | RAG 问答提示词 | ChatPromptTemplate |
| `query_expansion.py` | 查询扩写提示词 | PromptTemplate |

Skills 技能文件位于 `skills/` 目录，Markdown 格式，通过 user_settings.json 启用。

### 添加新厂商

`server/llm.py` 使用注册表模式，加新厂商只需一个装饰器：

```python
@register_provider("openai")
def _build_openai(config):
    return ChatOpenAI(api_key=..., **_build_kwargs(config))
```

## 工程质量

### 日志系统

- **Logger 工厂**：各模块通过 `get_logger(__name__)` 获取独立 Logger
- **双输出**：控制台彩色 + 文件轮转（10MB × 5 份）
- **请求追踪**：HTTP 中间件为每个请求生成 `request_id`，注入日志上下文
- **模块级别**：通过 user_settings.json 按模块名独立设置日志级别

```python
from server.logging_config import get_logger
logger = get_logger(__name__)
logger.info("消息")
```

### 错误处理

- **统一异常体系**（`app/errors.py`）：7 种业务异常，自动映射 HTTP 状态码
- **三层隔离**：用户看到 `message`，日志记录 `internal_detail`，完整堆栈写日志文件
- **全局异常处理器**：`AppException` 处理器 + 兜底 `Exception` 处理器

```python
from app.errors import NotFoundError, ValidationError

if not kb:
    raise NotFoundError("知识库不存在")
```

### 配置加载

`RAGConfig.from_settings()` 从 `data/user_settings.json` 加载配置，首次运行时自动创建默认配置文件。前端通过 `/settings/providers` API 管理厂商和模型。

### 文件安全

- **上传限制**：50MB 大小限制 + 文件类型白名单（38 种扩展名）
- **路径穿越防护**：文件名清理 + `resolve()` 校验
- **并发安全**：`knowledge_bases.json` 原子写入 + `fcntl.flock` 文件锁
- **自动清理**：`uploads/` 1 小时过期，`downloads/` 24 小时过期

### MCP 容错

- 逐服务器独立连接，单个失败不影响其他
- 每个服务器 10 秒超时保护
- 全部失败时 Agent 仍可使用内置工具
