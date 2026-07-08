# 墨问 - AI Agent 助手

> 基于 LangGraph + DeepSeek 的智能 Agent，支持知识库检索、联网搜索、Docker 沙盒代码执行、长期记忆与流式对话。

## 功能

- **Agent 自主决策**：LLM 自动判断是否需要调用工具（知识库检索 / 联网搜索 / 沙盒执行）
- **Docker 沙盒**：在隔离的 Linux 容器中执行代码、安装包、处理文件，支持文件上传/下载
- **知识库 RAG**：上传文档后自动切分入库，回答时精准定位相关内容
- **联网搜索**：通过 Tavily 实时搜索最新信息（需配置 API Key）
- **网页抓取**：抓取指定 URL 的网页内容并转为 Markdown
- **MCP 工具集成**：通过 Model Context Protocol 连接外部工具服务器
- **Skills 技能系统**：Markdown 格式的可扩展场景指导，Agent 按需参考
- **长期记忆**：SQLite 持久化记忆，自动提取用户事实/偏好/对话摘要
- **模型上下文窗口**：内置 50+ 模型官方上下文数据，支持按模型覆盖
- **实时 Token 统计**：流式对话中实时显示输入/输出 token 用量与进度条
- **多厂商切换**：DeepSeek / 智谱 AI / Kimi / 硅基流动，设置页面可视化管理
- **人格设定**：可自定义 Agent 性格与回答风格（如猫娘助手）
- **流式输出**：逐 token 输出，支持展示推理过程（DeepSeek 思考链）
- **工具调用可视化**：前端实时显示工具调用状态和结果
- **知识库管理**：创建、上传文档、重建向量库、删除，按类型（小说/技术/项目/通用）定制回答策略
- **Markdown 渲染**：代码块、表格、列表、图片等完整支持
- **会话持久化**：localStorage 保存对话历史和运行时设置
- **设置页面**：可视化管理厂商 API Key、模型选择、向量模型、人设、用户画像、记忆、MCP
- **定时任务**：APScheduler 定时执行 Agent 任务，支持 cron/间隔/单次触发，前端可视化管理
- **MCP 浏览器**：@playwright/mcp 集成，Agent 可浏览网页、截图、点击交互
- **网页抓取**：抓取指定 URL 的网页内容并转为 Markdown，可选抓取图片
- **测试覆盖**：pytest 187 个测试用例覆盖核心模块

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
| Embedding | 智谱 AI embedding-3 / 可自定义 |
| 向量库 | Chroma |
| 沙盒 | Docker SDK for Python（mowen-sandbox 自建镜像） |
| MCP | langchain-mcp-adapters + @playwright/mcp |
| 定时任务 | APScheduler (AsyncIOScheduler + SQLite) |
| API | FastAPI + SSE 流式 |
| 日志 | logging + RotatingFileHandler + RequestIdFilter 请求追踪 |
| 错误处理 | 统一异常体系 + 全局异常处理器 + lifespan 生命周期 |
| 数据库 | SQLite (WAL 模式 + 线程本地连接) |
| 会话持久化 | SQLite + localStorage 双写同步 |
| 测试 | pytest + pytest-asyncio + pytest-cov（187 个用例） |
| 部署 | Docker Compose（Nginx + Uvicorn 单容器） |

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

### 测试

```sh
# 运行全部测试
python -m pytest tests/ -v

# 带覆盖率报告
python -m pytest tests/ --cov=server --cov=app --cov-report=term-missing
```

### Docker 部署

```sh
# 构建镜像
docker build -t mowen-app:latest -f Dockerfile.app .
docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .

# 启动
docker compose up -d

# 访问 http://localhost（或配置 Nginx 反代）
```

## 项目结构

```
.
├── api.py                  # 启动入口
├── data/user_settings.json # 用户配置（首次运行自动生成）
├── pyproject.toml          # 依赖管理
│
├── server/                 # 核心引擎包
│   ├── __init__.py             公共 API
│   ├── core/                   基础设施层
│   │   ├── config.py               RAGConfig 配置（从 user_settings 加载）
│   │   ├── db.py                   SQLite 数据库封装（WAL + 线程本地连接）
│   │   ├── logging_config.py       日志模块（Logger 工厂 + RequestIdFilter）
│   │   ├── user_settings.py        用户配置管理器（默认值 + 合并 + 迁移）
│   │   ├── conversation_store.py    对话历史持久化
│   │   ├── scheduler.py            定时任务调度器（APScheduler）
│   │   └── scheduled_task_store.py  定时任务存储（SQLite）
│   ├── llm/                    LLM 抽象层
│   │   ├── factory.py              LLM 厂商工厂（注册表模式）
│   │   ├── embeddings.py           Embedding 模型
│   │   ├── provider_config.py      厂商预设配置
│   │   └── model_context.py        模型上下文窗口映射（50+ 模型官方数据）
│   ├── rag/                    RAG 管线层
│   │   ├── loader.py               文档加载
│   │   ├── splitter.py             文档切分
│   │   ├── vectorstore.py          Chroma 向量库
│   │   ├── knowledge_base.py       知识库元数据管理
│   │   └── chain.py                RAG 链构建 + 向量库构建 + 问答接口
│   ├── prompts/                提示词统一管理
│   │   ├── __init__.py             公共导出
│   │   ├── agent.py                Agent 系统提示词（段落组合）
│   │   ├── rag.py                  RAG 问答提示词
│   │   └── query_expansion.py      查询扩写提示词
│   ├── retrieval/              检索子包
│   │   ├── retriever.py            多查询检索
│   │   └── query_expansion.py      查询扩写
│   └── agent/                  Agent 子包
│       ├── graph.py                LangGraph ReAct Agent
│       ├── tools.py                14 个工具（搜索/沙盒/网页抓取/技能/MCP导出）
│       ├── sandbox.py               Docker 沙盒管理器
│       ├── mcp.py                   MCP 客户端（逐服务器容错）
│       ├── memory.py                长期记忆（提取 + 存储 + 检索）
│       └── skills.py                Skills 技能加载器
│
├── app/                    # FastAPI 路由层
│   ├── main.py                FastAPI 实例 + 中间件 + lifespan 生命周期
│   ├── errors.py              统一异常体系
│   ├── cleanup.py             文件清理（uploads/downloads 过期）
│   ├── models.py              Pydantic 数据模型
│   └── routes/                路由
│       ├── chat.py                对话接口（/chat/stream + 沙盒管理）
│       ├── config.py              配置与健康检查
│       ├── conversations.py       会话历史 CRUD + 批量同步
│       ├── files.py               文件上传/下载（200MB+类型白名单）
│       ├── knowledge_bases.py     知识库 CRUD
│       ├── memory.py              记忆管理 API
│       ├── scheduled_tasks.py     定时任务 CRUD + 调度控制
│       └── settings.py            厂商/模型/向量模型/人设/画像/MCP 配置 API
│
├── skills/                 # 技能文件（Markdown，自动扫描）
│   ├── data_analysis.md         数据分析工作流程
│   ├── document-conversion.md   文档格式转换工作流程
│   ├── web_scraping.md          网页爬取工作流程
│   ├── find_skills/             技能搜索指导
│   ├── mermaid-diagrams/        Mermaid 图表绘制
│   └── word-document/           Word 文档操作
│
├── Dockerfile.sandbox       # 沙盒 Docker 镜像定义
├── Dockerfile.app           # 应用镜像（前端+后端+Nginx 多阶段构建）
├── docker-compose.yml       # Docker Compose 编排配置
├── deploy/                  # 部署配置（nginx.conf / start.sh / 部署脚本）
├── tests/                  # 测试用例（187 个 pytest 测试）
│
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── api/                API 调用（chat/config/settings/knowledgeBase/conversations）
│       ├── components/         组件
│       │   ├── chat/              ChatArea / ChatInput / ChatMessage / ContextPanel
│       │   ├── home/              HomeHero
│       │   ├── layout/            AppSidebar / ChatHistoryPanel / KnowledgeBasePanel
│       │   └── settings/          McpSettings / MemorySettings / ModelSettings / PersonaSettings / ProfileSettings / RetrievalSettings
│       ├── composables/        组合式函数（useChat / useConfig / useKnowledgeBase / useSettings）
│       ├── stores/             Pinia 状态管理（chat + knowledgeBase）
│       ├── types/              类型定义
│       └── views/              页面（HomeView / SettingsView / ScheduledTasksView）
│
├── data/                   # 文档上传目录 + 用户配置 + 记忆数据库
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
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp", "--headless", "--browser", "chromium", "--output-dir", "downloads/playwright"],
      "transport": "stdio"
    }
  },
  "embedding_custom": {
    "enabled": false,
    "base_url": "",
    "api_key": "",
    "model": ""
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
| `model_context_overrides` | 模型级覆盖：上下文窗口、最大输出、temperature、thinking 等 |
| `chunking` | 文档切分：块大小、重叠、章节切分 |
| `retrieval` | 检索参数：top_k、查询扩写 |
| `context` | 全局上下文窗口限制（0 = 使用模型默认值） |
| `agent` | Agent 工具配置：tavily_api_key 启用联网搜索 |
| `mcp_servers` | 外部 MCP 服务器配置（逐服务器容错） |
| `skills` | 启用的技能列表，对应 skills/*.md 文件 |
| `logging` | 日志级别、文件路径、按模块独立级别 |
| `vector_store` | Chroma 持久化目录 |
| `embedding_custom` | 自定义向量模型：独立 base_url / api_key / model，启用后优先级最高 |
| `persona` | 人格设定（如猫娘助手） |
| `user_profile` | 用户画像（职业、技能等上下文） |
| `memory` | 长期记忆配置（最大条数、包含画像等） |

### 模型上下文窗口

`server/model_context.py` 内置 50+ 模型的官方上下文窗口数据，来源包括 DeepSeek、智谱 AI、Kimi、Qwen、OpenAI 等官方网站。运行时自动匹配当前模型，支持三级优先级：

1. **用户覆盖** (`model_context_overrides`) — 最高优先级
2. **内置数据** — 从官方文档采集
3. **未知** — 默认 128K

前端聊天框实时显示 token 用量进度条：`(输入 + 输出) / 上下文窗口`，颜色随用量变化（绿→黄→红）。

### 长期记忆

Agent 在每轮对话后自动提取值得长期记住的信息（用户事实、偏好、对话摘要），存入 SQLite 数据库。下次对话时自动注入系统提示词。通过设置页面可查看、删除记忆条目。

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
| `sandbox_edit_file` | 精确替换文件中的文本片段 |
| `sandbox_read_file` | 读取沙盒中的文件 |
| `sandbox_list_files` | 列出沙盒目录 |
| `sandbox_export_file` | 导出沙盒文件为下载链接（图片直接渲染） |
| `export_mcp_file` | 将 MCP 浏览器文件导入沙盒（截图/PDF/下载） |
| `list_mcp_files` | 列出 MCP 浏览器输出的所有文件 |
| `search_knowledge_base` | 搜索用户上传的知识库 |
| `search_web` | 联网搜索实时信息（Tavily） |
| `fetch_webpage` | 抓取指定网址的网页内容（可选抓取图片） |
| `load_skill` | 加载技能的完整指导内容 |
| `search_skills` | 从 skills.sh 搜索开源技能 |
| `install_skill` | 安装技能到项目并自动启用 |

### 提示词工程

所有提示词统一在 `server/prompts/` 包中集中管理，支持段落级组合与动态注入。

#### Agent 系统提示词 (`server/prompts/agent.py`)

采用**段落组合模式**，最终 prompt = 身份 + 人设 + 技能 + 时间 + 记忆 + 画像 + 上传文件：

| 段落 | 来源 | 说明 |
|------|------|------|
| 身份声明 | 静态 | "你是墨问，一个智能 AI Agent 助手" |
| 能力清单 | 静态 | 14 个工具的用途与使用场景 |
| 沙盒说明 | 静态 | Linux 容器环境、预装工具、pip/apt 镜像 |
| 工具原则 | 静态 | 何时用沙盒/知识库/搜索/抓取/直接回答 |
| 文件处理 | 静态 | 上传文件自动导入 /workspace/，压缩包先解压 |
| 多步骤 | 静态 | 分步执行：写代码→运行→改错→再运行 |
| 防循环 | 静态 | 同工具失败 ≤3 次，总调用 ≤15 次 |
| 输出规范 | 静态 | 文本/代码/文件/错误/格式的输出约定 |
| 人设 | 动态 | 从 `user_settings.json` 的 `persona` 注入（如猫娘） |
| 技能 | 动态 | 从 `skills/*.md` 加载启用的技能指导 |
| 时间 | 动态 | 当前日期时间 |
| 记忆 | 动态 | 从 SQLite 检索的相关长期记忆 |
| 画像 | 动态 | 从 `user_settings.json` 的 `user_profile` 注入 |
| 文件 | 动态 | 当前上传文件的列表和说明 |

#### RAG 问答提示词 (`server/prompts/rag.py`)

```
你是一个专业的智能文档问答助手。
- 忠实于上下文，不编造
- 标注来源【章节名】
- 结构化输出，分点/分段
- 信息不足时诚实说明
- 矛盾信息同时呈现并标注来源
```

#### 查询扩写提示词 (`server/prompts/query_expansion.py`)

从多角度生成语义相关但表达不同的检索查询，策略包括：关键词替换、视角转换、实体补全、句式变化。原始问题始终保留在检索查询中。

#### 记忆提取提示词 (`server/agent/memory.py`)

```
分析对话，提取 fact / preference / summary 三类记忆。
- 跳过临时闲聊
- 每条独立可理解
- 最多 N 条，宁缺毋滥
- 不与已有记忆重复
- 输出 JSON 数组
```

#### Skills 技能文件 (`skills/`)

Markdown 格式的可扩展场景指导，目录下所有 `.md` 文件自动扫描加载。当前包含：
- `data_analysis.md` - 数据分析工作流程（pandas + matplotlib）
- `document-conversion.md` - 文档格式转换（docx/pdf/xlsx/md/html 互转）
- `web_scraping.md` - 网页爬取工作流程（BeautifulSoup + httpx）
- `find_skills/` - 技能搜索指导
- `mermaid-diagrams/` - Mermaid 图表绘制
- `word-document/` - Word 文档操作

Agent 遇到相关任务时调用 `load_skill` 获取完整指导，按指导在沙盒中执行操作。新增技能只需在 `skills/` 目录创建 `.md` 文件即可。

### 添加新厂商

`server/llm/factory.py` 使用注册表模式，加新厂商只需一个装饰器：

```python
@register_provider("openai")
def _build_openai(config):
    return ChatOpenAI(api_key=..., **_build_kwargs(config))
```

## 工程质量

### 日志系统

- **Logger 工厂**：各模块通过 `get_logger(__name__)` 获取独立 Logger
- **双输出**：控制台彩色 + 文件轮转（10MB × 5 份）
- **请求追踪**：HTTP 中间件为每个请求生成 `request_id`，注入日志上下文（RequestIdFilter）
- **模块级别**：通过 user_settings.json 按模块名独立设置日志级别
- **第三方库降噪**：httpx/watchfiles/mcp/docker/chromadb 统一设为 WARNING

```python
from server.core.logging_config import get_logger
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

- **上传限制**：200MB 大小限制 + 文件类型白名单（40+ 种扩展名）
- **路径穿越防护**：文件名清理 + `resolve()` 校验
- **并发安全**：`knowledge_bases.json` 原子写入 + `fcntl.flock` 文件锁
- **自动清理**：`uploads/` 24 小时过期，`downloads/` 24 小时过期

### MCP 容错

- 逐服务器独立连接，单个失败不影响其他
- 每个服务器 30 秒超时保护
- 全部失败时 Agent 仍可使用内置工具

### 定时任务

基于 APScheduler 实现的定时任务系统：
- 支持 cron 表达式、固定间隔、单次触发三种模式
- 任务存储在 SQLite，重启后自动恢复
- 每个任务绑定一个 Agent 对话，到时自动执行并保存结果
- 前端可视化管理：创建/编辑/暂停/恢复/立即执行

### 向量模型配置

向量模型支持三种配置方式（优先级从高到低）：
1. **自定义配置**（`embedding_custom`）：独立 base_url / api_key / model，与厂商配置解耦
2. **厂商模型选择**（`embedding_model`）：从已配置 API Key 的厂商中选择 embedding 模型
3. **自动推断**：系统从所有厂商模型列表中自动查找 embedding 类模型

前端设置页「向量模型」tab 可视化管理，支持开关自定义配置、选择厂商模型。

### Docker 部署

#### 架构

```
         :80
           │
    ┌──────┴──────┐
    │   Nginx     │  ← 容器内，托管前端 + 反代 API
    │  静态文件    │     /  -> Vue SPA (try_files)
    │  /api/ 反代  │     /api/ -> 127.0.0.1:8000 (SSE: proxy_buffering off)
    └──────┬──────┘
    ┌──────┴──────┐
    │  Uvicorn    │  ← 同一容器内
    │  FastAPI    │
    └──────┬──────┘
           │ docker.sock (挂载宿主机)
    ┌──────┴──────┐
    │  沙盒容器    │  mowen-sandbox:latest
    │  (按需创建)  │  256MB / 最多3个 / 15min 超时
    └─────────────┘
```

#### 一键部署

```sh
# 本地构建 -> 传到服务器 -> 启动
chmod +x deploy/build-and-deploy.sh
./deploy/build-and-deploy.sh 服务器IP
```

#### 手动部署

```sh
# 1. 构建镜像
docker build -t mowen-app:latest -f Dockerfile.app .
docker build -t mowen-sandbox:latest -f Dockerfile.sandbox .

# 2. 启动
docker compose up -d

# 3. 访问
curl http://localhost/api/health
```

#### 日常运维

```sh
docker compose logs -f          # 查看日志
docker compose restart           # 重启
docker exec -it mowen-app bash   # 进入容器调试
```
