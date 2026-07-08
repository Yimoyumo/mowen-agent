"""Agent 提示词测试。

测试内容：
- get_agent_system_prompt 组装完整提示词
- 各段落存在（IDENTITY/TOOLS/SANDBOX/TOOL_PRINCIPLES/OUTPUT_RULES）
- 动态注入变量（skills/time/uploaded/persona/profile）
- 模板变量转义（不含未解析的 {xxx}）
"""

import re

import pytest

from server.prompts.agent import (
    get_agent_system_prompt,
    _IDENTITY,
    _TOOLS,
    _SANDBOX,
    _TOOL_PRINCIPLES,
    _OUTPUT_RULES,
)
from server.core.config import RAGConfig


class TestGetAgentSystemPrompt:
    """get_agent_system_prompt 测试。"""

    def test_basic_assembly(self):
        prompt = get_agent_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_identity(self):
        prompt = get_agent_system_prompt()
        assert "墨问" in prompt

    def test_contains_tools(self):
        prompt = get_agent_system_prompt()
        assert "sandbox_run" in prompt
        assert "search_knowledge_base" in prompt
        assert "fetch_webpage" in prompt
        assert "sandbox_export_file" in prompt

    def test_contains_sandbox_section(self):
        prompt = get_agent_system_prompt()
        assert "沙盒" in prompt
        assert "/workspace" in prompt

    def test_contains_tool_principles(self):
        prompt = get_agent_system_prompt()
        assert "何时用" in prompt

    def test_contains_output_rules(self):
        prompt = get_agent_system_prompt()
        assert "输出规范" in prompt

    def test_no_unresolved_template_vars(self):
        """提示词中不应有未解析的模板变量 {xxx}（排除文档中的示例 {filename}）。"""
        prompt = get_agent_system_prompt()
        # 匹配 {xxx} 但排除 {{xxx}}（已转义）
        unresolved = re.findall(r'(?<!\{)\{[a-z_][a-z_0-9]*\}(?!\})', prompt)
        # {filename} 出现在文档说明中，是正常的文字描述，不是模板变量
        real_unresolved = [v for v in unresolved if v not in ('{filename}',)]
        assert real_unresolved == [], f"发现未解析的模板变量: {real_unresolved}"

    def test_persona_injection(self):
        prompt = get_agent_system_prompt(persona_prompt="你是猫娘助手")
        assert "猫娘" in prompt

    def test_uploaded_files_injection(self):
        prompt = get_agent_system_prompt(uploaded_info="文件: test.txt")
        assert "test.txt" in prompt

    def test_memory_injection(self):
        prompt = get_agent_system_prompt(memory_prompt="用户喜欢 Python")
        assert "用户喜欢 Python" in prompt

    def test_profile_injection(self):
        prompt = get_agent_system_prompt(profile_prompt="skills: Python, Go")
        assert "Python" in prompt

    def test_time_present(self):
        prompt = get_agent_system_prompt()
        # 应该包含当前日期时间
        assert "2026" in prompt or "2025" in prompt  # 宽松匹配

    def test_contains_mcp_tools(self):
        """提示词包含 MCP 工具说明。"""
        prompt = get_agent_system_prompt()
        assert "export_mcp_file" in prompt
        assert "list_mcp_files" in prompt

    def test_contains_browser_tools(self):
        """提示词包含浏览器工具说明。"""
        prompt = get_agent_system_prompt()
        assert "browser_navigate" in prompt or "MCP" in prompt


class TestPromptSections:
    """各段落内容完整性测试。"""

    def test_identity(self):
        assert "墨问" in _IDENTITY

    def test_tools_has_all_tools(self):
        tool_names = [
            "sandbox_run", "sandbox_write_file", "sandbox_edit_file",
            "sandbox_read_file", "sandbox_list_files", "sandbox_export_file",
            "search_knowledge_base", "search_web", "fetch_webpage",
            "load_skill", "search_skills", "install_skill",
            "export_mcp_file", "list_mcp_files",
        ]
        for name in tool_names:
            assert name in _TOOLS, f"提示词缺少工具: {name}"

    def test_sandbox_has_limits(self):
        assert "512MB" in _SANDBOX or "内存" in _SANDBOX
        assert "超时" in _SANDBOX

    def test_tool_principles_has_when_to_use(self):
        assert "何时用沙盒" in _TOOL_PRINCIPLES
        assert "何时用知识库" in _TOOL_PRINCIPLES
        assert "何时用浏览器" in _TOOL_PRINCIPLES

    def test_output_rules_has_format(self):
        assert "代码" in _OUTPUT_RULES or "Markdown" in _OUTPUT_RULES
        assert "文件交付" in _OUTPUT_RULES or "导出" in _OUTPUT_RULES
