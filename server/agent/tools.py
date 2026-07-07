"""Agent 工具集。

定义可供 Agent 调用的工具函数：
- search_knowledge_base: 检索上传的知识库文档
- search_web: 联网搜索实时信息
- sandbox_run: 在 Docker 沙盒中执行 shell 命令
- sandbox_write_file / sandbox_read_file / sandbox_list_files: 沙盒文件操作
- search_skills / install_skill: 宿主机技能搜索与安装（不经过沙盒）
"""

import contextvars
import json
import subprocess
from pathlib import Path

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
def sandbox_edit_file(path: str, old_text: str, new_text: str) -> str:
    """精确替换文件中的某段文本（用于修改已有文件，避免全量重写）。
    path: 文件路径（如 /workspace/sort.py）
    old_text: 要替换的原始文本（必须与文件中的内容完全一致，包括缩进和换行）
    new_text: 替换后的新文本

    使用场景：
    - 修改代码中的某一行或某几行
    - 替换函数名、变量名
    - 修改配置文件中的某个值

    注意：
    - old_text 必须在文件中唯一匹配，如果有多处匹配会报错，请提供更多上下文使其唯一
    - 如果 old_text 不存在于文件中，会报错
    - 替换后文件会自动保存"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"

    # 读取当前内容
    current = sb.read_file(path)
    if current.startswith("（文件不存在"):
        return f"（文件不存在: {path}）"

    # 检查匹配
    count = current.count(old_text)
    if count == 0:
        # 提供附近内容帮助 Agent 定位
        preview = current[:500] if len(current) > 500 else current
        return f"（未找到要替换的文本。文件前 500 字符：\n{preview}）"
    if count > 1:
        return f"（匹配到 {count} 处，old_text 不唯一。请提供更多上下文使其唯一匹配）"

    # 执行替换
    new_content = current.replace(old_text, new_text, 1)
    sb.write_file(path, new_content)

    # 返回改动上下文（前后各几行）方便 Agent 确认
    idx = new_content.index(new_text)
    lines_before = new_content[:idx].count("\n")
    context_start = max(0, idx - 200)
    context_end = min(len(new_content), idx + len(new_text) + 200)
    context = new_content[context_start:context_end]

    return f"✓ 已替换 {path} (第 {lines_before + 1} 行)\n```{context}```"


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


@tool
def load_skill(skill_name: str) -> str:
    """加载指定技能的完整指导内容。

    系统提示词中列出了已启用的技能摘要，当你需要某个技能的详细工作流程时，
    调用此工具获取完整内容。

    适用场景：
    - 用户任务与某个技能相关，需要参考详细步骤
    - 不确定如何处理某类任务，想查看是否有相关技能指导

    参数:
        skill_name: 技能名称（从系统提示词的技能列表中获取）
    """
    from server.agent.skills import load_skill_detail

    return load_skill_detail(skill_name)


# ==================== 技能搜索与安装（宿主机工具，不经过沙盒） ====================


@tool
def search_skills(query: str) -> str:
    """从开源技能生态（skills.sh）搜索可用的 Agent 技能。

    在宿主机上执行 npx skills find，返回搜索结果。
    不经过沙盒，不需要 Docker。

    适用场景：
    - 用户问 "有没有技能可以做 X"
    - 用户想扩展 Agent 能力
    - 用户想找现成的方案而非从头写

    参数:
        query: 搜索关键词（如 "react performance"、"pr review"、"changelog"）
    """
    try:
        result = subprocess.run(
            ["npx", "-y", "skills", "find", query],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path.cwd()),
        )
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return "（搜索无结果）"

        if len(output) > 4000:
            output = output[:4000] + "\n\n... （结果过长已截断）"

        return output
    except subprocess.TimeoutExpired:
        return "（搜索超时，请稍后重试）"
    except FileNotFoundError:
        return "（npx 未安装，无法搜索技能）"
    except Exception as exc:
        return f"（搜索失败: {exc}）"


@tool
def install_skill(package: str) -> str:
    """安装开源技能到项目 skills/ 目录并自动启用。

    在宿主机上执行 npx skills add，安装到项目的 skills/ 目录下，
    并自动更新 user_settings.json 的 skills 数组。安装后可直接使用，无需重启。

    不经过沙盒，不需要 Docker。

    适用场景：
    - 用户想安装搜索到的技能
    - 用户提供了技能包名（如 owner/repo@skill-name）

    参数:
        package: 技能包名（如 "vercel-labs/agent-skills@vercel-react-best-practices"）
    """
    from server.agent.skills import list_available_skills
    from server.user_settings import user_settings
    from server.logging_config import get_logger

    logger = get_logger(__name__)

    # 安装前的技能列表
    before = set(list_available_skills())

    try:
        result = subprocess.run(
            ["npx", "-y", "skills", "add", package, "-y"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.cwd()),
        )

        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"（安装失败: {err or output[:500]}）"

        # 安装后的技能列表，找出新增的
        after = set(list_available_skills())
        new_skills = after - before

        if not new_skills:
            # 可能装到了用户目录而非项目目录，检查 ~/.agents/skills/
            home_skills = Path.home() / ".agents" / "skills"
            if home_skills.exists():
                # 找最新的目录
                dirs = sorted(home_skills.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                if dirs:
                    src = dirs[0]
                    dest = Path("skills") / src.name
                    if src.is_dir():
                        import shutil
                        shutil.copytree(src, dest)
                        new_skills = {src.name}

        if not new_skills:
            return f"安装命令已执行，但未检测到新技能。\n输出: {output[:500]}\n\n请检查技能是否安装到了其他目录。"

        # 自动更新 user_settings.json
        cfg = user_settings.load()
        skills_list = cfg.get("skills", [])
        for s in new_skills:
            if s not in skills_list:
                skills_list.append(s)
        cfg["skills"] = skills_list
        user_settings.save(cfg)

        skill_list_str = ", ".join(new_skills)
        logger.info("技能已安装并启用: %s", skill_list_str)

        return (
            f"✓ 技能安装成功: {skill_list_str}\n"
            f"已自动启用，可以直接使用。\n"
            f"调用 load_skill('{list(new_skills)[0]}') 可查看技能详细内容。"
        )

    except subprocess.TimeoutExpired:
        return "（安装超时，请稍后重试）"
    except FileNotFoundError:
        return "（npx 未安装，无法安装技能）"
    except Exception as exc:
        return f"（安装失败: {exc}）"


def get_agent_tools() -> list:
    """获取 Agent 可用工具列表。"""
    return [
        search_knowledge_base,
        search_web,
        fetch_webpage,
        sandbox_run,
        sandbox_write_file,
        sandbox_edit_file,
        sandbox_read_file,
        sandbox_list_files,
        sandbox_export_file,
        load_skill,
        search_skills,
        install_skill,
    ]
