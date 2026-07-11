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

from server.core.config import RAGConfig
from server.core.logging_config import get_logger
from server.retrieval.retriever import expand_and_retrieve
from server.rag.chain import _resolve_collection_name

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

    return "\n\n---\n\n".join(doc.page_content for i, doc in enumerate(docs))


@tool
def search_web(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """搜索互联网获取实时信息，返回搜索结果摘要。
    
    参数：
    - query: 搜索关键词
    - max_results: 返回结果数量（1-10，默认5）。简单问题用3即可，需要广泛调研时可用8-10
    - search_depth: 搜索深度，"basic"（快速摘要）或 "advanced"（深度搜索，内容更详细但更慢）
    
    使用建议：
    - 简单事实查询：max_results=3, search_depth="basic"
    - 常规搜索：max_results=5, search_depth="basic"（默认）
    - 深度调研：max_results=8, search_depth="advanced"
    
    适用场景：最新新闻、天气、股价、实时事件等知识库无法覆盖的动态信息。
    不适用场景：已上传知识库中的内容——这类问题请用 search_knowledge_base。"""
    config = _current_config.get()

    # 参数边界保护
    max_results = max(1, min(10, max_results))
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    # 有 Tavily API Key -> 用 Tavily
    if config.tavily_api_key:
        try:
            client = TavilyClient(api_key=config.tavily_api_key)
            result = client.search(query, search_depth=search_depth, max_results=max_results)
            if result.get("results"):
                return "\n\n".join(
                    f"【{r['title']}】({r['url']})\n{r['content']}"
                    for r in result["results"]
                )
        except Exception as exc:
            logger.warning("Tavily 搜索失败，降级到 Bing: query=%s err=%s", query, exc)

    # 降级方案：抓取 Bing 搜索结果
    return _bing_search(query, max_results)


def _bing_search(query: str, max_results: int = 5) -> str:
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
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Bing 搜索失败: query=%s err=%s", query, exc)
        return f"（搜索失败: {exc}）"

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Bing 搜索结果在 <li class="b_algo"> 中
    for item in soup.select("li.b_algo")[:max_results]:
        title_tag = item.select_one("h2 a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get("href", "")

        # 摘要在 <p> 或 .b_caption p 中
        snippet = ""
        snippet_tag = item.select_one(".b_caption p") or item.select_one("p")
        if snippet_tag:
            snippet = snippet_tag.get_text(strip=True)

        if title and link:
            results.append(f"【{title}】({link})\n{snippet}")

    if not results:
        return "（未找到相关搜索结果）"

    logger.info("Bing 降级搜索完成: query=%s results=%d", query, len(results))
    return "\n\n".join(results)


@tool
def fetch_webpage(url: str, include_images: bool = False) -> str:
    """抓取指定网页内容，返回正文文本（转换为 Markdown 格式）。
    支持：自动编码检测、HTML 清洗（去除脚本/导航/页脚）、正文区域提取。
    参数 include_images 控制是否下载页面中的图片：
      - False（默认）：仅抓取文本内容，速度快
      - True：同时下载页面中的图片到沙盒 /workspace/（最多 10 张），不渲染
    如果 URL 直接指向图片（Content-Type: image/*），图片会保存到沙盒供后续处理。
    适用场景：用户给了具体网址，需要读取页面内容；或搜索到结果后想看详情。
    不适用场景：搜索关键词--请用 search_web。"""
    from server.agent.sandbox import get_or_create

    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动，无法抓取网页）"

    # httpx + beautifulsoup4 + html2text + chardet 已预装在沙盒镜像中
    script = r'''import sys
import os
import httpx
import chardet
from bs4 import BeautifulSoup
import html2text
from urllib.parse import urljoin, urlparse

url = sys.argv[1]
include_images = len(sys.argv) > 2 and sys.argv[2] == "1"

# ---------- 1. 发送 HTTP 请求 ----------
try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = httpx.get(url, timeout=20, follow_redirects=True, headers=headers)
    resp.raise_for_status()
except Exception as e:
    print(f"ERROR: 请求失败: {e}")
    sys.exit(1)

# ---------- 2. 判断是否为图片 ----------
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
    filepath = "/workspace/" + filename
    with open(filepath, "wb") as f:
        f.write(resp.content)
    print("IMAGE_FILE:" + filepath)
    sys.exit(0)

# ---------- 3. 编码检测 ----------
raw = resp.content
if resp.encoding and resp.encoding.lower() != "iso-8859-1":
    html_text = raw.decode(resp.encoding, errors="replace")
else:
    detected = chardet.detect(raw)
    encoding = detected.get("encoding") or "utf-8"
    html_text = raw.decode(encoding, errors="replace")

# ---------- 4. HTML 清洗 ----------
soup = BeautifulSoup(html_text, "lxml")

for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe", "form"]):
    tag.decompose()

for selector in ["nav", "footer", "header[class*='site']", "aside",
                 "[role='navigation']", "[role='banner']", "[role='complementary']"]:
    for el in soup.select(selector):
        el.decompose()

# ---------- 5. 下载页面中的图片（仅当 include_images=True 时）----------
downloaded_images = []
img_tags = soup.find_all("img") if include_images else []
for img in img_tags[:10]:
    src = img.get("src") or img.get("data-src")
    if not src:
        continue
    img_url = urljoin(url, src)
    if not img_url.startswith(("http://", "https://")):
        continue
    try:
        img_resp = httpx.get(img_url, timeout=15, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
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
        fname = "page_img_" + str(len(downloaded_images)) + ext
        fpath = "/workspace/" + fname
        with open(fpath, "wb") as f:
            f.write(img_resp.content)
        downloaded_images.append(fpath)
        img["src"] = "DOWNLOADED:" + fpath
    except Exception:
        pass

# ---------- 6. HTML -> Markdown ----------
main = soup.find("main") or soup.find("article") or soup.body or soup
html_content = str(main)

h = html2text.HTML2Text()
h.ignore_links = False
h.ignore_images = not include_images
h.ignore_emphasis = False
h.body_width = 0
h.unicode_snob = True
text = h.handle(html_content)

# ---------- 7. 后处理 ----------
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

# 输出图片标记 + 文本
if downloaded_images:
    img_marker = "IMAGES:" + ",".join(downloaded_images)
    print(img_marker)
    print("---TEXT---")

if not text:
    print("（页面无正文内容）")
else:
    MAX = 15000
    if len(text) > MAX:
        text = text[:MAX] + "\n\n... （内容过长，已截断，共 " + str(len(text)) + " 字符）"
    print(text)
'''
    sb.write_file("/workspace/_fetch.py", script)
    safe_url = url.replace("'", "'\"'\"'")
    img_flag = "1" if include_images else "0"
    exit_code, output = sb.exec(f"python3 /workspace/_fetch.py '{safe_url}' {img_flag}", timeout=30)
    output = output.strip()
    sb.exec("rm -f /workspace/_fetch.py")

    if exit_code != 0:
        logger.warning("抓取网页失败: url=%s exit=%d", url, exit_code)
        return f"（抓取失败: {output[:300]}）"

    if not output:
        return "（页面无内容）"

    # 处理输出中的图片标记
    # 情况 1: URL 直接指向图片 → 保存到沙盒即可，不导出渲染
    if output.startswith("IMAGE_FILE:"):
        img_path = output[len("IMAGE_FILE:"):].strip()
        fname = img_path.rsplit("/", 1)[-1] if "/" in img_path else img_path
        logger.info("抓取图片已保存到沙盒: %s", img_path)
        return f"图片已保存到沙盒 {img_path}（{fname}）。后续可用 sandbox_run 对图片进行处理、分析等。"

    # 情况 2: 页面中包含已下载的图片
    image_paths = []
    text_content = output
    if output.startswith("IMAGES:"):
        parts = output.split("\n---TEXT---\n", 1)
        if len(parts) == 2:
            img_line = parts[0]
            text_content = parts[1]
            img_paths_str = img_line[len("IMAGES:"):].strip()
            image_paths = [p.strip() for p in img_paths_str.split(",") if p.strip()]

    image_note = ""
    if image_paths:
        fnames = [p.rsplit("/", 1)[-1] for p in image_paths]
        image_note = f"\n\n（页面中的 {len(image_paths)} 张图片已保存到沙盒，文件名: {', '.join(fnames)}）"

    logger.info("抓取网页成功: %s (%d 字符, %d 张图片)", url, len(text_content), len(image_paths))
    return text_content + image_note





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
            timeout=120,
            cwd=str(Path.cwd()),
            stdin=subprocess.DEVNULL,
            env={
                **__import__('os').environ,
                'npm_config_registry': 'https://registry.npmmirror.com/',
            },
        )
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return "（搜索无结果）"

        if len(output) > 4000:
            output = output[:4000] + "\n\n... （结果过长已截断）"

        return output
    except subprocess.TimeoutExpired:
        logger.warning("搜索技能超时: query=%s", query)
        return "（搜索超时，请稍后重试）"
    except FileNotFoundError:
        logger.warning("npx 未安装，无法搜索技能")
        return "（npx 未安装，无法搜索技能）"
    except Exception as exc:
        logger.warning("搜索技能失败: query=%s err=%s", query, exc)
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
    from server.core.user_settings import user_settings
    from server.core.logging_config import get_logger

    logger = get_logger(__name__)

    # 安装前的技能列表
    before = set(list_available_skills())

    try:
        result = subprocess.run(
            ["npx", "-y", "skills", "add", package, "-y"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(Path.cwd()),
            stdin=subprocess.DEVNULL,
            env={
                **__import__('os').environ,
                'GIT_HTTP_LOW_SPEED_LIMIT': '1000',
                'GIT_HTTP_LOW_SPEED_TIME': '120',
                'npm_config_registry': 'https://registry.npmmirror.com/',
            },
        )

        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"（安装失败: {err or output[:500]}）"

        # 安装后的技能列表，找出新增的
        # 现在同时扫描项目和用户目录，无需手动复制
        after = set(list_available_skills())
        new_skills = after - before

        if not new_skills:
            return f"安装命令已执行，但未检测到新技能。\n输出: {output[:500]}\n\n请检查技能是否安装到了其他目录。"

        # 技能目录会被自动扫描，无需手动更新配置
        skill_list_str = ", ".join(new_skills)
        logger.info("技能已安装并自动启用: %s", skill_list_str)

        return (
            f"✓ 技能安装成功: {skill_list_str}\n"
            f"已自动启用（技能目录会被自动扫描），可以直接使用。\n"
            f"调用 load_skill('{list(new_skills)[0]}') 可查看技能详细内容。"
        )

    except subprocess.TimeoutExpired:
        logger.warning("安装技能超时: package=%s", package)
        return "（安装超时，请稍后重试）"
    except FileNotFoundError:
        logger.warning("npx 未安装，无法安装技能")
        return "（npx 未安装，无法安装技能）"
    except Exception as exc:
        logger.error("安装技能失败: package=%s err=%s", package, exc)
        return f"（安装失败: {exc}）"


@tool
def export_mcp_file(filename: str) -> str:
    """将 MCP 浏览器工具产生的文件（截图、PDF、下载等）导入沙盒。

    MCP 浏览器（@playwright/mcp）的截图/PDF/下载文件存储在 downloads/playwright/ 目录，
    此工具将文件从宿主机导入到沙盒的 /workspace/ 目录。

    导入后，文件位于 /workspace/{filename}，你可以：
    - 用 sandbox_read_file 查看文本文件
    - 用 sandbox_export_file 导出下载链接给用户
    - 用 sandbox_run 对文件做进一步处理

    适用场景：
    - 浏览器截图后想保存到沙盒处理或导出给用户
    - 浏览器下载了文件想提供给用户
    - 浏览器生成的 PDF 需要交付

    参数:
        filename: 文件名（仅文件名，不含路径），如 "screenshot.png"、"report.pdf"
    """
    from pathlib import Path

    from server.agent.sandbox import get_or_create

    mcp_output_dir = Path("downloads/playwright")
    if not mcp_output_dir.exists():
        return f"（MCP 输出目录不存在: {mcp_output_dir}，浏览器可能还未产生任何文件）"

    # 安全校验：防止路径穿越
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in (".", ".."):
        return f"（无效的文件名: {filename}）"

    src_path = mcp_output_dir / safe_name
    if not src_path.exists():
        # 列出可用文件帮助 Agent 定位
        files = list(mcp_output_dir.iterdir())
        if not files:
            return f"（MCP 输出目录为空，文件 '{safe_name}' 不存在）"
        file_list = "\n".join(f"  - {f.name}" for f in sorted(files))
        return f"（文件 '{safe_name}' 不存在，当前可用文件:\n{file_list}）"

    # 获取当前会话的沙盒
    session_id = _current_session_id.get()
    sb = get_or_create(session_id) if session_id else None
    if sb is None:
        return "（沙盒未启动）"

    # 导入到沙盒 /workspace/
    dest = sb.import_file(str(src_path))
    if dest is None:
        return f"（导入沙盒失败: 无法将 {safe_name} 导入沙盒）"

    # 提示 Agent 下一步该怎么做
    img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')
    if safe_name.lower().endswith(img_exts):
        return f"✓ 文件已导入沙盒: /workspace/{safe_name}（图片）\n如需导出给用户，请调用 sandbox_export_file('/workspace/{safe_name}')"
    else:
        return f"✓ 文件已导入沙盒: /workspace/{safe_name}\n如需导出给用户，请调用 sandbox_export_file('/workspace/{safe_name}')"


@tool
def list_mcp_files() -> str:
    """列出 MCP 浏览器工具产生的所有输出文件（截图、PDF、下载等）。
    在导出文件之前先查看有哪些可用文件。"""
    from pathlib import Path

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
        export_mcp_file,
        list_mcp_files,
        load_skill,
        search_skills,
        install_skill,
    ]
