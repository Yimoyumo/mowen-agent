"""Agent 工具集（异步化 + 宿主机直操/权限审批）。

定义可供 Agent 调用的异步工具：
- run_command: 在宿主机/工作区执行 shell 命令（需权限审批）
- write_file / edit_file / read_file / list_files / export_file: 工作区文件操作
- ask_user: 主动提问（统一 HITL 机制）
- fetch_webpage: 原生抓取网页（宿主机进程内，不再写脚本进沙盒）
- search_knowledge_base / search_web / load_skill / search_skills / install_skill
- export_mcp_file / list_mcp_files: MCP 浏览器文件导入工作区

关键变化：
- 所有工具改为 @tool + async def，通过统一执行器（executor）访问工作区。
- 危险命令 / 文件操作先经权限引擎 classify，需审批时走 interaction.request（HITL）。
- 不再依赖 server/agent/sandbox 模块（工具层）。
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import uuid
from pathlib import Path

from langchain_core.tools import tool
from tavily import TavilyClient

from server.agent import interaction, ops_audit
from server.agent.executor import get_executor
from server.agent.executor.base import new_op_id
from server.agent.permissions import (
    Decision,
    apply_approval_mode,
    classify_command,
    classify_file_op,
)
from server.core.config import RAGConfig
from server.core.logging_config import get_logger
from server.retrieval.retriever import expand_and_retrieve
from server.rag.chain import _resolve_collection_name

logger = get_logger(__name__)


# ==================== 运行时上下文 ====================

_current_kb_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "kb_id", default=None
)
_current_config: contextvars.ContextVar[RAGConfig | None] = contextvars.ContextVar(
    "config", default=None
)
# session_id 用于工作区跨消息持久化
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)


def set_agent_context(kb_id: str | None, config: RAGConfig, session_id: str | None = None) -> None:
    """设置 Agent 工具的运行时上下文（由 chat_stream 调用）。"""
    _current_kb_id.set(kb_id)
    _current_config.set(config)
    _current_session_id.set(session_id)


def get_tools_config() -> dict:
    """获取执行器配置（executor_config），供权限 / 超时等读取。"""
    config = _current_config.get()
    return dict(config.executor_config) if config else {}


def _get_config() -> RAGConfig:
    config = _current_config.get()
    return config or RAGConfig.from_settings()


def _get_session_id() -> str:
    return _current_session_id.get() or "default"


def _get_executor():
    return get_executor(_get_config())


# ==================== 超时与审批辅助 ====================

def _command_timeout(command: str, ex_cfg: dict) -> int:
    """根据命令类型 + executor_config.command_timeout 判断超时秒数。

    沿用旧逻辑：pip/apt/git clone/npm install 180s、python 60s、其他用基础值。
    """
    base = int(ex_cfg.get("command_timeout") or 30)
    cmd_lower = command.strip().lower()
    if any(k in cmd_lower for k in ["pip install", "apt", "git clone", "npm install", "cargo"]):
        return max(base, 180)
    if any(k in cmd_lower for k in ["python", "sh ", "./"]):
        return max(base, 60)
    return base


def _scope_key(kind: str, scope_op: str | None, target: str, workspace) -> str:
    """计算用于审批 scope 缓存的归一化 pattern。

    - 文件操作（kind == "file"）：`{op}:{解析后的绝对路径}`（op=read/write/edit/list/export）
    - 其他（run / host_tool）：命令前两 token 归一化（如 "pip install *"）
    """
    if kind == "file" and scope_op:
        return interaction.normalize_file_pattern(scope_op, target, workspace)
    return interaction.normalize_pattern(target)


async def _approve_or_deny(
    *,
    op_id: str,
    tool: str,
    kind: str,
    target: str,
    risk: str,
    cls,
    session_id: str,
    ex_cfg: dict,
    scope_op: str | None = None,
    workspace=None,
) -> bool:
    """对需审批的操作执行审批流程（含 scope 缓存命中直接放行）。

    Args:
        scope_op: 文件操作的具体 op（kind=="file" 时传 read/write/edit/list/export）；否则为 None
        workspace: 会话工作区根（用于文件操作路径归一化）

    Returns:
        True=允许继续；False=拒绝/超时/无UI（不执行）。
    """
    approval_timeout = int(ex_cfg.get("approval_timeout") or 120)
    scope_key = _scope_key(kind, scope_op, target, workspace)

    # 审批 scope 缓存命中 → 跳过提问直接放行（不限 kind）
    if scope_key and interaction.check_scope_cache(session_id, scope_key):
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": tool, "kind": kind,
            "target": target, "risk": risk, "status": "approved",
        })
        return True

    res = await interaction.request(
        "approval",
        {
            "tool": tool,
            "kind": kind,
            "command": target,
            "decision": "ask",
            "reason": risk,
            "timeout": approval_timeout,
            "scope_key": scope_key,
        },
        session_id,
        approval_timeout,
    )

    if res["status"] == "answered":
        if res.get("approved"):
            ops_audit.record({
                "op_id": op_id, "session_id": session_id, "tool": tool, "kind": kind,
                "target": target, "risk": risk, "status": "approved",
            })
            return True
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": tool, "kind": kind,
            "target": target, "risk": risk, "status": "denied",
        })
        return False
    if res["status"] == "timeout":
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": tool, "kind": kind,
            "target": target, "risk": risk, "status": "timeout",
        })
        return False
    # no_ui / cancelled：无法审批
    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": tool, "kind": kind,
        "target": target, "risk": risk, "status": "timeout",
    })
    return False


# 子进程 env 白名单：绝不透传服务进程完整 env（防 API Key 等敏感信息泄露），
# 模式对齐 server/agent/executor/host.py 的白名单做法。
_SUBPROCESS_ENV_BASE: dict[str, str] = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LANG": "C.UTF-8",
    "TZ": "Asia/Shanghai",
    "HOME": str(Path.home()),
}


def _sanitize_env(env: dict | None = None) -> dict[str, str]:
    """构造子进程 env 白名单（在必要项基础上合并调用方显式传入的 env）。"""
    return {**_SUBPROCESS_ENV_BASE, **(env or {})}


async def _async_subprocess(cmd: list[str], timeout: int, env: dict | None = None) -> tuple[str, str, bool]:
    """异步执行子进程（超时则 kill，env 白名单），返回 (stdout, stderr, timed_out)。"""
    full_env = _sanitize_env(env)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.cwd()),
            env=full_env,
        )
    except FileNotFoundError:
        return "", "命令不存在", False
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), False
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return "", "（执行超时，已终止）", True


# ==================== 知识库 / 搜索工具 ====================

@tool
async def search_knowledge_base(query: str) -> str:
    """在用户已上传的知识库中搜索相关内容，返回最相关的文档片段。
    适用场景：用户询问文档、小说、技术手册、项目资料等知识库内的问题。
    不适用场景：实时新闻、天气、股价等动态信息——这类问题请用 search_web。"""
    config = _get_config()
    kb_id = _current_kb_id.get()

    if not kb_id:
        return "（当前未选择知识库，无法检索。请告诉用户需要先选择一个知识库。）"

    def _retrieve():
        collection_name = _resolve_collection_name(kb_id, config)
        return expand_and_retrieve(query, collection_name, config)

    docs = await asyncio.to_thread(_retrieve)

    if not docs:
        return "（知识库中未找到相关内容）"
    return "\n\n---\n\n".join(doc.page_content for i, doc in enumerate(docs))


@tool
async def search_web(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """搜索互联网获取实时信息，返回搜索结果摘要。

    参数：
    - query: 搜索关键词
    - max_results: 返回结果数量（1-10，默认5）
    - search_depth: "basic"（快速摘要）或 "advanced"（深度搜索）
    """
    config = _get_config()
    max_results = max(1, min(10, max_results))
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    if config.tavily_api_key:
        try:
            client = TavilyClient(api_key=config.tavily_api_key)
            result = await asyncio.to_thread(
                lambda: client.search(query, search_depth=search_depth, max_results=max_results)
            )
            if result.get("results"):
                return "\n\n".join(
                    f"【{r['title']}】({r['url']})\n{r['content']}"
                    for r in result["results"]
                )
        except Exception as exc:
            logger.warning("Tavily 搜索失败，降级到 Bing: query=%s err=%s", query, exc)

    return await _bing_search(query, max_results)


async def _bing_search(query: str, max_results: int = 5) -> str:
    """无 Tavily API Key 时的降级方案：抓取 Bing 搜索结果页。"""
    from urllib.parse import quote_plus
    import httpx
    from bs4 import BeautifulSoup

    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Bing 搜索失败: query=%s err=%s", query, exc)
        return f"（搜索失败: {exc}）"

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for item in soup.select("li.b_algo")[:max_results]:
        title_tag = item.select_one("h2 a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get("href", "")
        snippet = ""
        snippet_tag = item.select_one(".b_caption p") or item.select_one("p")
        if snippet_tag:
            snippet = snippet_tag.get_text(strip=True)
        if title and link:
            results.append(f"【{title}】({link})\n{snippet}")

    if not results:
        return "（未找到相关搜索结果）"
    return "\n\n".join(results)


# ==================== 命令 / 文件工具 ====================

@tool
async def run_command(command: str) -> str:
    """在会话工作区中执行任意 shell 命令，返回完整输出。

    适用场景：代码执行、数据处理、软件包安装与测试、文件操作、运行脚本。
    提示：
    - 多个步骤的命令用 && 或分号串联；需要多个命令时可多次调用，工作区状态保持。
    - 危险命令（如删除根目录、格式化磁盘、关机重启等）会被安全策略拒绝。
    - 部分命令（rm/cp/mv/pip/apt/curl 等）需要用户审批，通过后才能执行。"""
    config = _get_config()
    ex_cfg = get_tools_config()
    session_id = _get_session_id()
    executor = _get_executor()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    timeout = _command_timeout(command, ex_cfg)
    op_id = new_op_id()

    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_command(command, ws, ex_cfg), approval_mode)

    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "run_command", "kind": "run",
        "target": command, "risk": cls.reason,
        "status": "pending_approval" if cls.decision == Decision.ASK else "running",
    })

    if cls.decision == Decision.DENY:
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "run_command", "kind": "run",
            "target": command, "risk": cls.reason, "status": "denied",
            "finished_at": int(__import__("time").time()),
        })
        return f"（该操作被安全策略拒绝：{cls.reason}。请不要重试相同命令，告知用户原因。）"

    if cls.decision == Decision.ASK:
        ok = await _approve_or_deny(
            op_id=op_id, tool="run_command", kind="run", target=command,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
        )
        if not ok:
            return _approval_fail_message(command, session_id)
        # 审批通过后标记 running
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "run_command", "kind": "run",
            "target": command, "risk": cls.reason, "status": "running",
        })

    interaction.emit({
        "type": "exec_update", "op_id": op_id, "session_id": session_id,
        "tool": "run_command", "status": "running", "target": command,
    })

    try:
        result = await executor.run(session_id, command, timeout=timeout, op_id=op_id)
    except Exception as exc:
        logger.error("命令执行失败: cmd=%s err=%s", command[:100], exc)
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "run_command", "kind": "run",
            "target": command, "risk": cls.reason, "status": "failed",
            "output": str(exc), "finished_at": int(__import__("time").time()),
        })
        return f"（执行失败: {exc}）"

    output = result.output.strip() or "（无输出）"
    if len(output) > 4000:
        output = output[:4000] + "\n\n... （输出过长已截断）"

    if result.cancelled:
        status = "killed"
    elif result.timed_out:
        status = "timeout"
    elif result.exit_code != 0:
        status = "failed"
    else:
        status = "succeeded"

    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "run_command", "kind": "run",
        "target": command, "risk": cls.reason, "status": status,
        "exit_code": result.exit_code, "output": output, "finished_at": int(__import__("time").time()),
    })
    interaction.emit({
        "type": "exec_update", "op_id": op_id, "session_id": session_id,
        "tool": "run_command", "status": status, "target": command,
    })

    if result.cancelled:
        return "（操作已被取消，已停止执行）"
    prefix = "" if result.exit_code == 0 else f"（exit_code={result.exit_code}）\n"
    return prefix + output


def _approval_fail_message(command: str, session_id: str) -> str:
    """审批被拒 / 超时 / 无UI 时的返回文案（Agent 据此向用户解释）。"""
    return "（该操作未获得用户批准，已放弃执行。请向用户说明需要确认的原因，或改用用户已授权的方式完成此任务。）"


@tool
async def write_file(path: str, content: str) -> str:
    """在工作区中创建或全量覆盖文件。
    path: 文件路径（相对路径基于工作区根，如 "hello.py"）
    content: 文件内容"""
    executor = _get_executor()
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_file_op("write", path, ws, ex_cfg), approval_mode)

    if cls.decision == Decision.DENY:
        return f"（文件操作被安全策略拒绝：{cls.reason}）"
    if cls.decision == Decision.ASK:
        op_id = new_op_id()
        ok = await _approve_or_deny(
            op_id=op_id, tool="write_file", kind="file", target=path,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
            scope_op="write", workspace=ws,
        )
        if not ok:
            return _approval_fail_message(path, session_id)

    try:
        await executor.write_file(session_id, path, content)
    except ValueError as exc:
        return f"（写入失败: {exc}）"
    except Exception as exc:
        logger.warning("写入文件失败: path=%s err=%s", path, exc)
        return f"（写入失败: {exc}）"
    return f"✓ 已写入 {path}"


@tool
async def edit_file(path: str, old_text: str, new_text: str) -> str:
    """精确替换文件中的某段文本（用于修改已有文件，避免全量重写）。
    path: 工作区文件路径
    old_text: 要替换的原始文本（必须与文件内容完全一致，包括缩进和换行）
    new_text: 替换后的新文本
    注意：
    - old_text 必须唯一匹配；有多处匹配会报错，请提供更多上下文
    - 替换后文件自动保存"""
    executor = _get_executor()
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_file_op("write", path, ws, ex_cfg), approval_mode)

    if cls.decision == Decision.DENY:
        return f"（文件操作被安全策略拒绝：{cls.reason}）"
    if cls.decision == Decision.ASK:
        op_id = new_op_id()
        ok = await _approve_or_deny(
            op_id=op_id, tool="edit_file", kind="file", target=path,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
            scope_op="edit", workspace=ws,
        )
        if not ok:
            return _approval_fail_message(path, session_id)

    try:
        current = await executor.read_file(session_id, path)
    except Exception:
        current = ""
    if current.startswith("（文件不存在"):
        return f"（文件不存在: {path}）"

    count = current.count(old_text)
    if count == 0:
        preview = current[:500] if len(current) > 500 else current
        return f"（未找到要替换的文本。文件前 500 字符：\n{preview}）"
    if count > 1:
        return f"（匹配到 {count} 处，old_text 不唯一。请提供更多上下文使其唯一匹配）"

    new_content = current.replace(old_text, new_text, 1)
    try:
        await executor.write_file(session_id, path, new_content)
    except Exception as exc:
        return f"（写入失败: {exc}）"

    idx = new_content.index(new_text)
    lines_before = new_content[:idx].count("\n")
    context_start = max(0, idx - 200)
    context_end = min(len(new_content), idx + len(new_text) + 200)
    context = new_content[context_start:context_end]
    return f"✓ 已替换 {path} (第 {lines_before + 1} 行)\n```{context}```"


@tool
async def read_file(path: str) -> str:
    """读取工作区中的文件内容。"""
    executor = _get_executor()
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_file_op("read", path, ws, ex_cfg), approval_mode)
    if cls.decision == Decision.DENY:
        return f"（文件操作被安全策略拒绝：{cls.reason}）"
    if cls.decision == Decision.ASK:
        op_id = new_op_id()
        ok = await _approve_or_deny(
            op_id=op_id, tool="read_file", kind="file", target=path,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
            scope_op="read", workspace=ws,
        )
        if not ok:
            return _approval_fail_message(path, session_id)
    try:
        return await executor.read_file(session_id, path)
    except Exception as exc:
        return f"（读取失败: {exc}）"


@tool
async def list_files(path: str = "") -> str:
    """列出工作区目录中的文件（ls -lah 风格）。"""
    executor = _get_executor()
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_file_op("list", path or ".", ws, ex_cfg), approval_mode)
    if cls.decision == Decision.DENY:
        return f"（文件操作被安全策略拒绝：{cls.reason}）"
    if cls.decision == Decision.ASK:
        op_id = new_op_id()
        ok = await _approve_or_deny(
            op_id=op_id, tool="list_files", kind="file", target=path,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
            scope_op="list", workspace=ws,
        )
        if not ok:
            return _approval_fail_message(path, session_id)
    try:
        return await executor.list_dir(session_id, path)
    except Exception as exc:
        return f"（列出目录失败: {exc}）"


@tool
async def export_file(path: str) -> str:
    """将工作区中的文件导出为下载链接，方便用户下载到本地。
    Agent 完成文件生成后应调用此工具，然后将返回的下载链接提供给用户。
    图片文件（.png/.jpg/.svg/.gif）会直接在聊天中渲染显示，其他文件显示为下载链接。"""
    executor = _get_executor()
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    approval_mode = ex_cfg.get("approval_mode", "ask_dangerous")
    ws = executor.workspace_root(session_id)
    cls = apply_approval_mode(classify_file_op("export", path, ws, ex_cfg), approval_mode)
    if cls.decision == Decision.DENY:
        return f"（文件操作被安全策略拒绝：{cls.reason}）"
    if cls.decision == Decision.ASK:
        op_id = new_op_id()
        ok = await _approve_or_deny(
            op_id=op_id, tool="export_file", kind="file", target=path,
            risk=cls.reason, cls=cls, session_id=session_id, ex_cfg=ex_cfg,
            scope_op="export", workspace=ws,
        )
        if not ok:
            return _approval_fail_message(path, session_id)

    result = await executor.export_file(session_id, path)
    if result is None:
        return f"（导出失败: 文件不存在或无法读取 - {path}）"
    token, filename = result
    url = f"/api/download/{token}/{filename}"
    img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')
    if filename.lower().endswith(img_exts):
        return f"✓ 图片已导出，在下方渲染：\n![{filename}]({url})"
    return f"✓ 文件已导出: [{filename}]({url}) （点击下载）"


@tool
async def ask_user(question: str, options: list[str] | None = None, multi_select: bool = False) -> str:
    """主动向用户提问，获取回答后再继续。

    使用时机：
    - 缺少关键信息、无法推进任务时
    - 需要在多个方案之间做抉择时
    - 用户需求有歧义时

    使用的注意事项：
    - **一次只问一个清晰问题**，不要连问多个
    - 选项控制在 2-4 个，不要把选择权全部推给用户
    - 用户未及时回答时，基于合理假设继续，并在回复中明确说明假设
    - **不要反复追问**同一问题

    参数：
    - question: 要问的问题（清晰、具体）
    - options: 可选的选项列表（2-4 个）；不传则开放回答
    - multi_select: 是否允许多选（默认 False）"""
    session_id = _get_session_id()
    ex_cfg = get_tools_config()
    ask_timeout = int(ex_cfg.get("ask_timeout") or 300)

    res = await interaction.request(
        "ask_user",
        {
            "question": question,
            "options": options or [],
            "multi_select": multi_select,
        },
        session_id,
        ask_timeout,
    )

    if res["status"] == "answered":
        ans = res.get("answer", "")
        return f"用户回答：{ans}"
    if res["status"] == "timeout":
        return "（用户暂未回答，请基于合理假设继续，并在回复中明确说明假设）"
    # no_ui / cancelled
    return "（当前为非流式/无人值守场景，无法提问。请基于合理假设继续并说明假设，或告知用户切换到交互模式后重试。）"


# ==================== 抓取网页（原生实现） ====================

_MAX_IMAGE_COUNT = 10
_MAX_PAGE_CHARS = 15000

_ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def _fetch_url(url: str, include_images: bool, executor, session_id: str) -> tuple[str, list[str]]:
    """抓取网页正文（原生实现），返回 (markdown文本, 已下载图片路径列表)。"""
    import httpx
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_ARTICLE_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        return f"ERROR: 请求失败: {exc}", []

    # 直接指向图片
    content_type = resp.headers.get("content-type", "").lower()
    is_image = content_type.startswith("image/")
    if is_image:
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1]
        if not ext:
            ext = "." + content_type.split("/")[-1].split(";")[0]
            if ext == ".jpeg":
                ext = ".jpg"
        filename = "fetched_" + str(abs(hash(url)) % 100000) + ext
        try:
            await executor.write_bytes(session_id, filename, resp.content)
            return f"IMAGE_FILE:{filename}", []
        except Exception as exc:
            return f"ERROR: 图片保存失败: {exc}", []

    # 编码检测
    raw = resp.content
    html_text = None
    if resp.encoding and resp.encoding.lower() != "iso-8859-1":
        html_text = raw.decode(resp.encoding, errors="replace")
    else:
        try:
            import chardet
            detected = chardet.detect(raw)
            enc = detected.get("encoding") or "utf-8"
            html_text = raw.decode(enc, errors="replace")
        except Exception:
            html_text = raw.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    for selector in ["nav", "footer", "header[class*='site']", "aside",
                     "[role='navigation']", "[role='banner']", "[role='complementary']"]:
        for el in soup.select(selector):
            el.decompose()

    # 下载页面图片（可选）
    downloaded_paths: list[str] = []
    if include_images:
        img_tags = soup.find_all("img")[:_MAX_IMAGE_COUNT]
        for i, img in enumerate(img_tags):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            img_url = urljoin(url, src)
            if not img_url.startswith(("http://", "https://")):
                continue
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_ARTICLE_HEADERS) as c:
                    img_resp = await c.get(img_url)
                    img_resp.raise_for_status()
                img_ct = img_resp.headers.get("content-type", "").lower()
                if not img_ct.startswith("image/"):
                    continue
                ext = os.path.splitext(urlparse(img_url).path)[1]
                if not ext:
                    ext = "." + img_ct.split("/")[-1].split(";")[0]
                    if ext == ".jpeg":
                        ext = ".jpg"
                if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
                    continue
                fname = f"page_img_{i}{ext}"
                await executor.write_bytes(session_id, fname, img_resp.content)
                downloaded_paths.append(fname)
            except Exception:
                continue

    # HTML -> Markdown
    main = soup.find("main") or soup.find("article") or soup.body or soup
    html_content = str(main)
    text = _html_to_markdown(html_content, include_images)

    # 后处理：压缩空行
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = []
    blank = 0
    for line in lines:
        if line.strip() == "":
            blank += 1
            if blank <= 2:
                cleaned.append("")
        else:
            blank = 0
            cleaned.append(line)
    text = "\n".join(cleaned).strip()

    if len(text) > _MAX_PAGE_CHARS:
        text = text[:_MAX_PAGE_CHARS] + f"\n\n... （内容过长，已截断，共 {len(text)} 字符）"
    return text, downloaded_paths


def _html_to_markdown(html: str, include_images: bool) -> str:
    """HTML 转 Markdown（优先 html2text，缺失时降级为 bs4 粗转）。"""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = not include_images
        h.ignore_emphasis = False
        h.body_width = 0
        h.unicode_snob = True
        return h.handle(html)
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n", strip=True)


@tool
async def fetch_webpage(url: str, include_images: bool = False) -> str:
    """抓取指定网页内容，返回正文文本（转换为 Markdown 格式）。
    支持自动编码检测、HTML 清洗（去除脚本/导航/页脚）、正文区域提取。
    参数 include_images 控制是否下载页面中的图片：
      - False（默认）：仅抓取文本内容，速度快
      - True：同时下载页面中的图片到工作区（最多 10 张），不渲染
    如果 URL 直接指向图片（Content-Type: image/*），图片会保存到工作区供后续处理。
    适用场景：用户给了具体网址，需要读取页面内容；或搜索到结果后想看详情。"""
    executor = _get_executor()
    session_id = _get_session_id()

    text, image_paths = await _fetch_url(url, include_images, executor, session_id)

    if text.startswith("ERROR:"):
        return f"（抓取失败: {text[len('ERROR:'):].strip()}）"
    if text.startswith("IMAGE_FILE:"):
        fname = text[len("IMAGE_FILE:"):].strip()
        return f"图片已保存到工作区 {fname}。后续可用 run_command 对图片进行处理、分析等。"
    if not text:
        return "（页面无正文内容）"

    image_note = ""
    if image_paths:
        image_note = f"\n\n（页面中的 {len(image_paths)} 张图片已保存到工作区，文件名: {', '.join(image_paths)}）"
    logger.info("抓取网页成功: %s (%d 字符, %d 张图片)", url, len(text), len(image_paths))
    return text + image_note


# ==================== 技能工具 ====================

@tool
async def load_skill(skill_name: str) -> str:
    """加载指定技能的完整指导内容。
    系统提示词中列出了已启用的技能摘要，当你需要某个技能的详细工作流程时，
    调用此工具获取完整内容。
    参数: skill_name: 技能名称（从系统提示词的技能列表中获取）"""
    from server.agent.skills import load_skill_detail
    return await asyncio.to_thread(load_skill_detail, skill_name)


@tool
async def search_skills(query: str) -> str:
    """从开源技能生态（skills.sh）搜索可用的 Agent 技能。
    在宿主机上执行 npx skills find，返回搜索结果。不经过沙盒。
    参数: query: 搜索关键词"""
    # 只读网络查询：仅审计，不弹审批（避免无谓打扰）
    ex_cfg = get_tools_config()
    session_id = _get_session_id()
    op_id = new_op_id()
    cmd = f"npx -y skills find {query}"
    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "search_skills", "kind": "host_tool",
        "target": cmd, "risk": "只读技能搜索", "status": "running",
    })

    stdout, stderr, timed_out = await _async_subprocess(
        ["npx", "-y", "skills", "find", query],
        timeout=120,
        env={"npm_config_registry": "https://registry.npmmirror.com/"},
    )
    if timed_out:
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "search_skills", "kind": "host_tool",
            "target": cmd, "risk": "只读技能搜索", "status": "timeout", "finished_at": int(__import__("time").time()),
        })
        return "（搜索超时，请稍后重试）"
    output = (stdout.strip() or stderr.strip())
    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "search_skills", "kind": "host_tool",
        "target": cmd, "risk": "只读技能搜索", "status": "succeeded",
        "output": output, "finished_at": int(__import__("time").time()),
    })
    if not output:
        return "（搜索无结果）"
    if len(output) > 4000:
        output = output[:4000] + "\n\n... （结果过长已截断）"
    return output


@tool
async def install_skill(package: str) -> str:
    """安装开源技能到项目 skills/ 目录并自动启用。
    在宿主机上执行 npx skills add，安装到项目 skills/ 目录并自动启用。
    这是写宿主机 skills/ 目录的操作，**始终需要用户审批**。
    参数: package: 技能包名"""
    from server.agent.skills import list_available_skills

    ex_cfg = get_tools_config()
    session_id = _get_session_id()
    op_id = new_op_id()
    cmd = f"npx -y skills add {package} -y"
    risk = "安装技能（写入 skills/ 目录）"

    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
        "target": cmd, "risk": risk, "status": "pending_approval",
    })

    # 必审：始终保持用户确认
    approval_timeout = int(ex_cfg.get("approval_timeout") or 120)
    res = await interaction.request(
        "approval",
        {
            "tool": "install_skill", "kind": "host_tool", "command": cmd,
            "decision": "ask", "reason": risk, "timeout": approval_timeout,
        },
        session_id,
        approval_timeout,
    )
    if res["status"] == "answered" and res.get("approved"):
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
            "target": cmd, "risk": risk, "status": "approved",
        })
    else:
        status = "denied" if res["status"] == "answered" else "timeout"
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
            "target": cmd, "risk": risk, "status": status, "finished_at": int(__import__("time").time()),
        })
        return _approval_fail_message(cmd, session_id)

    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
        "target": cmd, "risk": risk, "status": "running",
    })

    before = set(await asyncio.to_thread(list_available_skills))
    stdout, stderr, timed_out = await _async_subprocess(
        ["npx", "-y", "skills", "add", package, "-y"],
        timeout=600,
        env={
            "GIT_HTTP_LOW_SPEED_LIMIT": "1000",
            "GIT_HTTP_LOW_SPEED_TIME": "120",
            "npm_config_registry": "https://registry.npmmirror.com/",
        },
    )
    if timed_out:
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
            "target": cmd, "risk": risk, "status": "timeout", "finished_at": int(__import__("time").time()),
        })
        return "（安装超时，请稍后重试）"
    output = stdout.strip()
    if "命令不存在" in stderr and not output:
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
            "target": cmd, "risk": risk, "status": "failed", "finished_at": int(__import__("time").time()),
        })
        return "（npx 未安装，无法安装技能）"

    after = set(await asyncio.to_thread(list_available_skills))
    new_skills = after - before
    if not new_skills:
        ops_audit.record({
            "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
            "target": cmd, "risk": risk, "status": "failed", "output": output[:500],
            "finished_at": int(__import__("time").time()),
        })
        return f"安装命令已执行，但未检测到新技能。\n输出: {output[:500]}\n\n请检查技能是否安装到了其他目录。"
    skill_list_str = ", ".join(new_skills)
    ops_audit.record({
        "op_id": op_id, "session_id": session_id, "tool": "install_skill", "kind": "host_tool",
        "target": cmd, "risk": risk, "status": "succeeded", "output": f"新增技能: {skill_list_str}",
        "finished_at": int(__import__("time").time()),
    })
    logger.info("技能已安装并自动启用: %s", skill_list_str)
    return (
        f"✓ 技能安装成功: {skill_list_str}\n"
        f"已自动启用（技能目录会被自动扫描），可以直接使用。\n"
        f"调用 load_skill('{list(new_skills)[0]}') 可查看技能详细内容。"
    )


# ==================== MCP 文件工具 ====================

@tool
async def export_mcp_file(filename: str) -> str:
    """将 MCP 浏览器工具产生的文件（截图、PDF、下载等）导入工作区。

    MCP 浏览器（@playwright/mcp）的截图/PDF/下载文件存储在下载目录 downloads/playwright/，
    此工具将文件从宿主机导入到当前会话工作区。

    导入后，文件位于工作区中，你可以：
    - 用 read_file 查看文本文件
    - 用 export_file 导出下载链接给用户
    - 用 run_command 对文件做进一步处理

    参数: filename: 文件名（仅文件名，不含路径），如 "screenshot.png"、"report.pdf"
    """
    mcp_output_dir = Path("downloads/playwright")
    if not mcp_output_dir.exists():
        return f"（MCP 输出目录不存在: {mcp_output_dir}，浏览器可能还未产生任何文件）"

    safe_name = Path(filename).name
    if safe_name != filename or safe_name in (".", ".."):
        return f"（无效的文件名: {filename}）"

    src_path = mcp_output_dir / safe_name
    if not src_path.exists():
        files = list(mcp_output_dir.iterdir())
        if not files:
            return f"（MCP 输出目录为空，文件 '{safe_name}' 不存在）"
        file_list = "\n".join(f"  - {f.name}" for f in sorted(files))
        return f"（文件 '{safe_name}' 不存在，当前可用文件:\n{file_list}）"

    executor = _get_executor()
    session_id = _get_session_id()
    dest = await executor.import_file(session_id, str(src_path))
    if dest is None:
        return f"（导入工作区失败: 无法将 {safe_name} 导入工作区）"

    img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')
    label = "（图片）" if safe_name.lower().endswith(img_exts) else ""
    return f"✓ 文件已放入工作区: {dest}{label}\n如需导出给用户，请调用 export_file('{dest}')"


@tool
async def list_mcp_files() -> str:
    """列出 MCP 浏览器工具产生的所有输出文件（截图、PDF、下载等）。
    在导出文件之前先查看有哪些可用文件。"""
    mcp_output_dir = Path("downloads/playwright")
    if not mcp_output_dir.exists():
        return "（MCP 输出目录不存在，浏览器可能还未产生任何文件）"
    files = sorted(mcp_output_dir.iterdir())
    if not files:
        return "（MCP 输出目录为空，还没有任何文件）"
    lines = []
    for f in files:
        if f.is_file():
            size_kb = f.stat().st_size / 1024
            lines.append(f"  - {f.name} ({size_kb:.1f} KB)")
        elif f.is_dir():
            lines.append(f"  - {f.name}/ (目录)")
    return "MCP 浏览器输出文件:\n" + "\n".join(lines)


# ==================== 工具列表 ====================

def get_agent_tools() -> list:
    """获取 Agent 可用工具列表。"""
    return [
        run_command,
        write_file,
        edit_file,
        read_file,
        list_files,
        export_file,
        ask_user,
        fetch_webpage,
        search_knowledge_base,
        search_web,
        load_skill,
        search_skills,
        install_skill,
        export_mcp_file,
        list_mcp_files,
    ]
