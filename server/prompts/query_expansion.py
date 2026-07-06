"""查询扩写提示词模块。

从 server/retrieval/query_expansion.py 中提取，
统一用 PromptTemplate 管理，支持 question 变量注入。
"""

from langchain_core.prompts import PromptTemplate


# ==================== 系统消息（SystemMessage 用）====================

EXPANSION_SYSTEM_MSG = "你是一个专业的语义检索查询扩写助手，擅长从多角度生成高质量的检索查询。"


# ==================== 查询扩写提示词模板 ====================

_QUERY_EXPANSION_TEXT = """你是一个专业的查询扩写助手，用于优化向量数据库的检索效果。
请根据用户的问题，从不同角度生成 2 个语义相关但表达方式不同的检索查询。

## 扩写策略

- **关键词替换**：用同义词或相关概念替换原始关键词
- **视角转换**：从不同角度描述同一信息需求
- **实体补全**：补充问题中隐含的相关实体名称
- **句式变化**：使用陈述句、疑问句等不同句式

## 要求

- 保持原问题的核心意图不变
- 每个查询单独占一行
- 不要输出编号、解释或任何多余内容
- 查询应当是简洁的检索短语，而非完整长句

用户问题：{question}

相关查询："""


# PromptTemplate 实例（支持 {question} 变量注入）
QUERY_EXPANSION_PROMPT = PromptTemplate.from_template(_QUERY_EXPANSION_TEXT)
