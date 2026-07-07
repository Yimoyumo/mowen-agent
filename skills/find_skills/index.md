---
name: find_skills
description: 搜索和安装开源 Agent 技能（来自 skills.sh 生态），用户想找新能力或扩展功能时使用
keywords: [技能, skill, 安装, 搜索, find, add, 扩展, 能力, install]
---

# 技能发现与安装

帮助用户从开源技能生态（skills.sh）搜索和安装新技能，扩展 Agent 的能力。

## 适用场景

当用户：
- 问 "有没有技能可以做 X" / "能找到做 X 的技能吗"
- 说 "我想扩展功能" / "有没有现成的方案"
- 问某个特定领域能否通过技能增强（如测试、部署、设计等）
- 想知道还有哪些技能可用

## 工作流程

### 第 1 步：理解用户需求

识别用户想要的能力：
1. 领域（如 React、测试、设计、部署）
2. 具体任务（如写测试、创建图表、审查 PR）
3. 是否足够常见，可能有现成技能

### 第 2 步：搜索技能

调用 `search_skills` 工具搜索：

```
search_skills(query="react performance")
```

工具会在宿主机上执行 `npx skills find` 并返回结果。

搜索结果格式：
```
Install with npx skills add <owner/repo@skill>

vercel-labs/agent-skills@vercel-react-best-practices
└ https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

示例：
- 用户问 "怎么优化 React 性能" → `search_skills("react performance")`
- 用户问 "能帮忙审查 PR 吗" → `search_skills("pr review")`
- 用户问 "我想生成 changelog" → `search_skills("changelog")`

### 第 3 步：展示结果

找到相关技能后，向用户展示：
1. 技能名称和功能描述
2. 安装命令
3. skills.sh 链接

示例回复：

```
我找到了一个可能适合的技能！"vercel-react-best-practices" 提供了
来自 Vercel 工程团队的 React 和 Next.js 性能优化指南。

了解更多：https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

### 第 4 步：安装技能

用户确认后，调用 `install_skill` 工具安装：

```
install_skill(package="vercel-labs/agent-skills@vercel-react-best-practices")
```

工具会：
1. 在宿主机执行 `npx skills add` 安装到项目 `skills/` 目录
2. 自动更新 `user_settings.json` 的 `skills` 数组
3. 返回安装结果和技能描述

安装成功后告知用户：
- 技能已安装并自动启用
- 可以直接使用，无需重启
- 调用 `load_skill(技能名)` 可以查看技能详细内容

### 第 5 步：未找到技能时

如果没有匹配的技能：
1. 诚实告知没有找到
2. 主动提供直接帮助
3. 建议用户可以自己创建技能

## 常见技能分类

搜索时可以参考这些分类：

| 分类 | 示例关键词 |
|------|-----------|
| Web 开发 | react, nextjs, typescript, css, tailwind |
| 测试 | testing, jest, playwright, e2e |
| DevOps | deploy, docker, kubernetes, ci-cd |
| 文档 | docs, readme, changelog, api-docs |
| 代码质量 | review, lint, refactor, best-practices |
| 设计 | ui, ux, design-system, accessibility |
| 效率工具 | workflow, automation, git |

## 注意事项

- 搜索时用具体关键词效果更好（"react testing" 比 "testing" 更精准）
- 热门来源：`vercel-labs/agent-skills`、`ComposioHQ/awesome-claude-skills`
- 浏览更多技能：https://skills.sh/
- 安装的技能直接放到项目 `skills/` 目录，跨会话持久
- 安装后自动启用，无需手动改配置或重启
