"""Agent 工具集。

定义可供 Agent 调用的工具函数：
- search_knowledge_base: 检索上传的知识库文档
- search_web: 联网搜索实时信息
- sandbox_run: 在 Docker 沙盒中执行 shell 命令
- sandbox_write_file / sandbox_read_file / sandbox_list_files: 沙盒文件操作
"""

import contextvars

from langchain_core.tools import tool
from tavily import TavilyClient

from server.config import RAGConfig
from server.logging_config import get_logger
from server.retrieval.retriever import expand_and_retrieve
from server.chain import _resolve_collection_name

logger = get_logger(__name__)

# 通过 contextvar 将 kb_id 和 config 从 chat_stream 传入工具
_current_kb_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "kb_id", default=None
)
_current_config: contextvars.ContextVar[RAGConfig] = contextvars.ContextVar(
    "config"
)
# session_id 用于沙盒跨消息持久化
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)


def set_agent_context(kb_id: str | None, config: RAGConfig, session_id: str | None = None) -> None:
    """设置 Agent 工具的运行时上下文（由 chat_stream 调用）。"""
    _current_kb_id.set(kb_id)
    _current_config.set(config)
    _current_session_id.set(session_id)


@tool
def search_knowledge_base(query: str) -> str:
    """在用户已上传的知识库中搜索相关内容，返回最相关的文档片段。
    适用场景：用户询问文档、小说、技术手册、项目资料等知识库内的问题。
    不适用场景：实时新闻、天气、股价等动态信息——这类问题请用 search_web。"""
    config = _current_config.get()
    kb_id = _current_kb_id.get()

    if not kb_id:
        return "（当前未选择知识库，无法检索。请告诉用户需要先选择一个知识库。）"

    collection_name = _resolve_collection_name(kb_id, config)
    docs = expand_and_retrieve(query, collection_name, config)

    if not docs:
        return "（知识库中未找到相关内容）"

    return "\n\n---\n\n".join(
        f"【来源 {i + 1}】{doc.page_content}"
        for i, doc in enumerate(docs)
    )


@tool
def search_web(query: str) -> str:
    """搜索互联网获取实时信息，返回搜索结果摘要。
    适用场景：最新新闻、天气、股价、实时事件等知识库无法覆盖的动态信息。
    不适用场景：已上传知识库中的内容——这类问题请用 search_knowledge_base。"""
    config = _current_config.get()

    if not config.tavily_api_key:
        return "（联网搜索功能未配置 API Key，请联系管理员设置 tavily_api_key）"

    try:
        client = TavilyClient(api_key=config.tavily_api_key)
        result = client.search(query, search_depth="basic", max_results=5)
    except Exception as exc:
        return f"（搜索失败: {exc}）"

    if not result.get("results"):
        return "（未找到相关搜索结果）"

    return "\n\n".join(
        f"【{r['title']}】({r['url']})\n{r['content']}"
        for r in result["results"]
    )


@tool
def fetch_webpage(url: str) -> str:
    """抓取指定网页内容，返回正文文本（转换为 Markdown 格式）。
    适用场景：用户给了具体网址，需要读取页面内容；或搜索到结果后想看详情。
    不适用场景：搜索关键词——请用 search_web。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动，无法抓取网页）"

    # httpx + html2text 已预装在沙盒镜像中
    script = '''import sys
import httpx, html2text

url = sys.argv[1]
try:
    resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
except Exception as e:
    print(f"ERROR: 请求失败: {e}")
    sys.exit(1)

h = html2text.HTML2Text()
h.ignore_links = False
h.ignore_images = True
h.body_width = 0
text = h.handle(resp.text)
# 去除过多空行
lines = [l.rstrip() for l in text.split("\\n")]
text = "\\n".join(lines)
# 截断
if len(text) > 8000:
    text = text[:8000] + "\\n\\n... （内容过长，已截断）"
print(text)
'''
    sb.write_file("/workspace/_fetch.py", script)
    # 用单引号包裹 URL 防止 shell 注入，并转义 URL 中的单引号
    safe_url = url.replace("'", "'\"'\"'")
    exit_code, output = sb.exec(f"python3 /workspace/_fetch.py '{safe_url}'", timeout=30)
    output = output.strip()
    sb.exec("rm -f /workspace/_fetch.py")

    if exit_code != 0:
        logger.warning("抓取网页失败: url=%s exit=%d", url, exit_code)
        return f"（抓取失败: {output[:300]}）"

    if not output:
        return "（页面无内容）"

    logger.info("抓取网页成功: %s (%d 字符)", url, len(output))
    return output


# ==================== 沙盒工具 ====================
# 依赖 server/agent/sandbox.py 管理容器生命周期。
# Agent 对话开始时创建沙盒，对话结束销毁，同一对话中多次工具调用共享容器。


@tool
def sandbox_run(command: str) -> str:
    """在 Linux 沙盒中执行任意 shell 命令，返回完整输出。
    沙盒是一个独立的 Linux 容器，可执行 Python 脚本、pip install 包、文件操作等。
    适用场景：代码执行、数据处理、软件包安装与测试、文件操作、运行脚本。
    提示：多个步骤的命令用 && 或分号串联；需要多个命令时可多次调用，容器状态会保持。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动，请稍后重试）"

    # 根据命令类型智能判断超时时间
    # pip install / apt install / git clone 等耗时操作给 120 秒
    # 普通命令 30 秒
    cmd_lower = command.strip().lower()
    if any(k in cmd_lower for k in ["pip install", "apt", "git clone", "npm install", "cargo"]):
        timeout = 180
    elif any(k in cmd_lower for k in ["python", "sh ", "./"]):
        timeout = 60
    else:
        timeout = 30

    exit_code, output = sb.exec(command, timeout=timeout)
    output = output.strip() or "（无输出）"

    if len(output) > 4000:
        output = output[:4000] + "\n\n... （输出过长已截断）"

    prefix = "" if exit_code == 0 else f"（exit_code={exit_code}）\n"
    return prefix + output


@tool
def sandbox_write_file(path: str, content: str) -> str:
    """在沙盒中创建或覆盖文件。
    path: 文件路径（如 /workspace/hello.py）
    content: 文件内容"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"

    sb.write_file(path, content)
    return f"✓ 已写入 {path}"


@tool
def sandbox_read_file(path: str) -> str:
    """读取沙盒中的文件内容。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"
    return sb.read_file(path)


@tool
def sandbox_list_files(path: str = "/workspace") -> str:
    """列出沙盒目录中的文件。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"
    return sb.list_dir(path)


@tool
def sandbox_export_file(path: str) -> str:
    """将沙盒中的文件导出为下载链接，方便用户下载到本地。
    Agent 完成文件生成后应调用此工具，然后将返回的下载链接提供给用户。
    适用场景：生成图表、报告、代码文件、数据文件等需要交付给用户的文件。
    图片文件（.png/.jpg/.svg/.gif）会直接在聊天中渲染显示，其他文件显示为下载链接。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"

    result = sb.export_file(path)
    if result is None:
        return f"（导出失败: 文件不存在或无法读取 - {path}）"

    token, filename = result
    url = f"/api/download/{token}/{filename}"

    # 图片文件用 ![]() 语法直接在 Markdown 中渲染
    img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')
    if filename.lower().endswith(img_exts):
        return f"✓ 图片已导出，在下方渲染：\n![{filename}]({url})"

    return f"✓ 文件已导出: [{filename}]({url}) （点击下载）"


def get_agent_tools() -> list:
    """获取 Agent 可用工具列表。"""
    return [
        search_knowledge_base,
        search_web,
        fetch_webpage,
        sandbox_run,
        sandbox_write_file,
        sandbox_read_file,
        sandbox_list_files,
        sandbox_export_file,
    ]
