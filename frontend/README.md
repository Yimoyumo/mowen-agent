# 墨问 - 前端

墨问 AI 助手前端，基于 Vue 3 + TypeScript + Vite + Element Plus。

## 功能

- 多轮上下文对话（流式输出）
- 可选 RAG 知识库增强
- 多会话管理（创建/切换/删除）
- Markdown 渲染（代码高亮、表格、引用等）
- 知识库管理（创建/上传/重建/删除）

## 开发

```sh
npm install
npm run dev      # 启动开发服务器
npm run build    # 构建生产版本
npm run type-check  # 类型检查
```

## 目录结构

```
src/
├── api/           API 调用层
│   ├── config.ts      axios 实例配置
│   ├── configApi.ts   配置与健康检查
│   ├── knowledgeBaseApi.ts  知识库 CRUD
│   ├── chat.ts        对话流式接口
│   └── index.ts       统一导出
├── assets/        全局样式
├── components/    组件
│   ├── chat/          对话区（消息、输入框、上下文面板）
│   ├── home/          首页欢迎
│   └── layout/        布局（侧边栏、知识库面板、会话列表）
├── composables/   组合式函数（useChat, useConfig, useKnowledgeBase）
├── router/        路由
├── stores/        Pinia 状态管理（chat, knowledgeBase）
├── types/         TypeScript 类型定义
├── utils/         工具函数（markdown 渲染）
└── views/         页面视图
```
