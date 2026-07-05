# 墨问 - 智能文档问答

> 基于 DeepSeek + LangChain + Chroma 的通用 AI 助手，支持多轮对话与可选 RAG 知识库增强。

## 功能

- **多轮对话**：支持上下文连续对话，流式输出
- **RAG 增强（可选）**：选择知识库后自动检索相关文档增强回答
- **知识库管理**：创建、上传文档、重建向量库、删除
- **按类型定制提示词**：小说 / 技术文档 / 项目文档 / 通用文档，不同类型使用不同回答策略
- **Markdown 渲染**：回答内容支持代码块、表格、列表等
- **会话持久化**：前端 localStorage 保存会话历史

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| 后端 | FastAPI + LangChain + Chroma |
| 模型 | DeepSeek（对话）+ 智谱 AI（Embedding） |

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
├── api.py                # API 入口（转发到 app 包）
├── app/                  # 后端应用
│   ├── main.py              FastAPI 实例与路由注册
│   ├── models.py            Pydantic 数据模型
│   └── routes/              路由模块
│       ├── chat.py             对话接口（/chat/stream + 旧版 /ask）
│       ├── config.py           配置与健康检查
│       └── knowledge_bases.py  知识库 CRUD
├── rag/                 # RAG 核心模块
│   ├── chat_chain.py        通用对话链（多轮 + 可选 RAG）
│   ├── chain.py             旧版 RAG 链
│   ├── config.py            配置管理
│   ├── llm.py               LLM 实例
│   ├── embeddings.py        向量模型
│   ├── retriever.py         检索 + 查询扩写
│   ├── query_expansion.py   查询扩写
│   ├── knowledge_base.py    知识库元数据管理
│   ├── loader.py            文档加载
│   ├── splitter.py          文档切分
│   ├── pipeline.py          RAG 完整流程
│   └── vectorstore_chroma.py  Chroma 向量库
├── frontend/            # Vue 3 前端
│   └── src/
│       ├── api/             API 调用（chat / config / knowledgeBase）
│       ├── components/      组件（chat / home / layout）
│       ├── composables/     组合式函数
│       ├── stores/          Pinia 状态管理
│       ├── types/           类型定义
│       ├── utils/           工具（Markdown 渲染）
│       └── views/           页面视图
├── data/               # 文档数据目录
├── notebook/           # 学习笔记（Jupyter）
├── vectorstore/        # Chroma 向量库持久化
└── config.json         # 模型与 RAG 配置
```

## 配置

在 `config.json` 中配置 API Key 和模型参数：

```json
{
  "zhipu_api_key": "your-zhipuai-key",
  "deepseek_api_key": "your-deepseek-key",
  "chat_provider": "deepseek",
  "chat_model": "deepseek-chat",
  "embedding_model": "embedding-3",
  "enable_query_expansion": true
}
```

## RAG 模式说明

选择知识库后自动启用 RAG 增强，不同知识库类型使用不同提示词策略：

| 类型 | 策略 |
|------|------|
| 小说 | 梳理人物关系、按时间线组织剧情、保持原文风格 |
| 技术文档 | 代码块标注语言、API 参数说明、步骤可复现 |
| 项目文档 | 需求追溯、设计决策背景、时效性标注 |
| 通用文档 | 灵活判断文档类型，适配不同内容 |
