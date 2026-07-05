# 墨问 - AI Agent 助手

> 基于 LangGraph + DeepSeek 的智能 Agent，支持知识库检索、联网搜索与流式对话。

## 功能

- **Agent 自主决策**：LLM 自动判断是否需要调用工具（知识库检索 / 联网搜索）
- **知识库 RAG**：上传文档后自动切分入库，回答时精准定位相关内容
- **联网搜索**：通过 Tavily 实时搜索最新信息（需配置 API Key）
- **流式输出**：逐 token 输出，支持展示推理过程（DeepSeek 思考链）
- **知识库管理**：创建、上传文档、重建向量库、删除，按类型（小说/技术/项目/通用）定制回答策略
- **Markdown 渲染**：代码块、表格、列表等完整支持
- **会话持久化**：localStorage 保存对话历史和运行时设置

## 架构

```
用户消息
  │
  ▼
┌──────────────────────────────────┐
│  LangGraph Agent (ReAct)         │
│                                  │
│  ┌────────┐    ┌──────────────┐  │
│  │  LLM   │◄──►│ Tool Executor│  │
│  │ 思考   │    │              │  │
│  │ 决策   │    │ 📚 知识库检索 │  │
│  │ 回答   │    │ 🌐 联网搜索  │  │
│  └────────┘    └──────────────┘  │
│      │                           │
│      ▼ 流式输出 (SSE)             │
└──────────────────────────────────┘
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| Agent 框架 | LangGraph (ReAct) |
| LLM | DeepSeek / 智谱 AI（可切换） |
| Embedding | 智谱 AI embedding-3 |
| 向量库 | Chroma |
| API | FastAPI + SSE 流式 |

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
├── config.json             # 全局配置
├── pyproject.toml          # 依赖管理
│
├── server/                 # 核心引擎包
│   ├── __init__.py             公共 API
│   ├── config.py               RAGConfig 配置
│   ├── llm.py                  LLM 厂商工厂（注册表模式）
│   ├── embeddings.py           Embedding 模型
│   ├── splitter.py             文档切分
│   ├── loader.py               文档加载
│   ├── knowledge_base.py       知识库元数据管理
│   ├── vectorstore_chroma.py   Chroma 向量库
│   ├── chain.py                RAG 链工具函数
│   ├── chat_chain.py           兼容层（重导出 agent.chat_stream）
│   ├── retrieval/              检索子包
│   │   ├── retriever.py            多查询检索
│   │   └── query_expansion.py      查询扩写
│   ├── agent/                  Agent 子包
│   │   ├── graph.py                LangGraph 状态图
│   │   └── tools.py                search_knowledge_base / search_web
│   └── legacy/                 旧版兼容（/ask 接口）
│       ├── chain.py
│       └── pipeline.py
│
├── app/                    # FastAPI 路由层
│   ├── main.py                FastAPI 实例
│   ├── models.py              Pydantic 数据模型
│   └── routes/                路由
│       ├── chat.py                对话接口（/chat/stream）
│       ├── config.py              配置与健康检查
│       └── knowledge_bases.py     知识库 CRUD
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
├── notebook/               # 学习笔记（Jupyter）
└── vectorstore/            # Chroma 持久化数据
```

## 配置

`config.json` 采用模块化分组：

```json
{
  "api_keys": {
    "zhipuai": "your-key",
    "deepseek": "your-key"
  },
  "model": {
    "provider": "deepseek",
    "chat": "deepseek-v4-flash",
    "embedding": "embedding-3"
  },
  "generation": {
    "temperature": 0.5,
    "max_tokens": 4096,
    "thinking": false
  },
  "chunking": {
    "size": 500,
    "overlap": 50,
    "chapter_split": false
  },
  "retrieval": {
    "top_k": 15,
    "query_expansion": false
  },
  "context": {
    "max_tokens": 0
  },
  "agent": {
    "tavily_api_key": ""
  }
}
```

| 分组 | 说明 |
|------|------|
| `api_keys` | 各厂商 API Key（也支持环境变量） |
| `model` | 模型选择：provider 切换 DeepSeek/智谱 |
| `generation` | 生成参数：temperature、max_tokens、thinking 等 |
| `chunking` | 文档切分：块大小、重叠、章节切分 |
| `retrieval` | 检索参数：top_k、查询扩写 |
| `context` | 上下文窗口限制（0 = 不限制） |
| `agent` | Agent 工具配置：tavily_api_key 启用联网搜索 |

## Agent 模式

Agent 自主决定何时调用工具，无需手动切换模式：

```
用户: "这个小说里最后谁赢了？"
Agent: → search_knowledge_base("最终结局") → 找到终章内容 → 回答

用户: "今天天气怎么样？"
Agent: → search_web("北京天气") → 返回实时天气

用户: "你好，介绍一下自己"
Agent: → 不调用工具，直接回答
```

### 添加新厂商

`server/llm.py` 使用注册表模式，加新厂商只需一个装饰器：

```python
@register_provider("openai")
def _build_openai(config):
    return ChatOpenAI(api_key=..., **_build_kwargs(config))
```
