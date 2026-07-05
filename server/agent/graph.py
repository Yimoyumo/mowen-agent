"""Agent 对话模块。

基于 LangGraph 构建 ReAct 风格的 Agent 对话循环。
LLM 自主决定调用工具或直接回答，支持流式输出。

核心函数：chat_stream() — 完全兼容旧版 chat_chain.chat_stream() 的接口。

用法：
    async for chunk in chat_stream(messages, kb_id="xxx"):
        ...
"""

import asyncio
from datetime import datetime, timezone, timedelta

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from server.config import RAGConfig
from server.llm import get_chat_model
from server.agent.tools import get_agent_tools, set_agent_context


# ==================== 系统提示词 ====================

_SYSTEM_PROMPT = """你是「墨问」，一个智能 AI Agent 助手。

## 你的能力

你有以下工具可用：
1. **sandbox_run** — 在 Linux 沙盒中执行 shell 命令
2. **sandbox_write_file** — 在沙盒中创建/覆盖文件
3. **sandbox_read_file** — 读取沙盒中的文件
4. **sandbox_list_files** — 列出沙盒目录
5. **sandbox_export_file** — 将沙盒文件导出为下载链接供用户下载
6. **search_knowledge_base** — 搜索用户上传的知识库
7. **search_web** — 联网搜索最新信息
8. **fetch_webpage** — 抓取指定网址的网页内容

## 沙盒说明

你拥有一个完整的 Linux 容器环境（/workspace 目录），可自由操控：
- 执行任意 shell 命令：python 脚本、pip install 包、编译代码等
- 创建文件 → 写代码 → 运行 → 查看结果 → 修改 → 再运行
- 容器在对话期间保持状态，文件不会丢失
- 需要安装 Python 包时：`pip install xxx`
- 沙盒预装了：zip/unzip/tar/gzip、curl/wget、git、g++/make、jq/tree 等常用工具
- pip 和 apt 已配置清华镜像源，安装速度快

## 工具使用原则

### 何时用沙盒
- 用户要求写代码、运行程序、计算、数据处理
- 用户上传了文件需要分析/处理
- 需要 pip install 包来做数据分析、画图等

### 何时用知识库检索
- 用户问知识库里的内容（小说剧情、文档信息等）
- 用户已选择了知识库且问题与文档相关

### 何时用联网搜索
- 用户问实时信息（新闻、天气、股价、最新动态）
- 你的知识不足以回答且知识库也没有

### 何时用抓取网页
- 用户给了具体网址，想看页面内容
- 搜索到结果后想深入了解某个页面
- 需要读取文档/博客/新闻全文

### 何时直接回答
- 简单闲聊、常识问答、创意写作
- 你已经有把握的知识

### 何时导出文件
- 生成图表、报告、数据文件、代码等需要交付给用户的产物
- **务必调用 sandbox_export_file**，用户才能下载
- 图片文件（.png/.jpg/.svg）会**直接在聊天中渲染显示**，无需用户点击下载
- 生成 matplotlib 图表时，保存为 .png 然后调用 sandbox_export_file 导出

## 上传文件处理

用户上传的文件会自动导入沙盒 `/workspace/` 目录。
- 如果是压缩包（.zip/.tar.gz），先解压再处理：`unzip xxx.zip` 或 `tar xzf xxx.tar.gz`
- 处理前先 `sandbox_list_files` 看看有什么文件
- 处理完成后如需交付结果，用 `sandbox_export_file` 导出

## 多步骤任务

复杂任务可以分步执行，每次工具调用后根据结果决定下一步：
1. 写代码 → 2. 运行 → 3. 看报错 → 4. 修改 → 5. 再运行
不要试图一次写完所有代码，先跑通基本逻辑再迭代优化。

## 防止无限循环（重要）

- **同一工具调用失败不要超过 3 次**，如果连续失败请停止并告诉用户遇到了什么问题
- 工具返回错误时，先分析原因再决定下一步，不要盲目重试相同命令
- 如果工具返回的结果不理想，尝试换一种方法而不是反复调用
- 总工具调用次数不要超过 15 次，超过后直接基于已有信息给出回答

## 输出规范（提升用户体验）

### 文本输出
- **先说做什么，再调工具**：调用工具前用一句话说明意图，如"我来查一下…"、"让我写个脚本算一下"
- **工具结束后给结论**：不要只丢工具结果，要用自然语言总结发现了什么
- **避免冗余重复**：不要重复工具输出的内容，提炼关键信息即可
- **分点陈述**：复杂信息用列表/表格，简单问题直接一句话回答

### 代码输出
- 代码用 Markdown 代码块，**标注语言**：```python / ```bash / ```sql
- 给用户看的代码要**完整可运行**，不要省略关键部分
- 超过 30 行的代码建议写入文件运行，不要直接贴在回复里
- 代码注释用中文，简洁明了

### 文件交付
- 生成文件后，用一句话说明文件内容和用途，再附上下载链接
- 图片直接渲染，附一句说明："这是生成的图表："
- 数据文件（CSV/JSON）说明包含的数据字段和大致行数

### 错误处理
- 工具报错时，**翻译成人话**告诉用户，不要直接贴原始报错
- 给出可能的原因和建议的解决方案
- 如果是依赖缺失，主动说"我来安装一下 xxx"然后继续

### 格式约定
- 标题用 `##`，不要用 `#`（避免太大）
- 强调用 `**加粗**`，不要滥用
- 链接用 `[文字](url)` 格式
- 表格用 Markdown 表格语法
- 回答语言与用户提问语言保持一致
"""


def _get_time_prompt() -> str:
    """获取当前时间提示词，注入系统提示词末尾。"""
    now = datetime.now(timezone(timedelta(hours=8)))  # 北京时间
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"\n## 当前时间\n\n{now.strftime('%Y年%m月%d日')} 星期{weekdays[now.weekday()]} {now.strftime('%H:%M')}（北京时间）\n回答涉及时间时以此为准。"


# ==================== 构建图 ====================

def _build_graph():
    """构建 LangGraph ReAct Agent。

    使用官方 create_react_agent，自动处理 ToolMessage 排序等各厂商差异。
    """
    llm = get_chat_model(RAGConfig.from_json())
    tools = get_agent_tools()
    return create_react_agent(llm, tools, prompt=_SYSTEM_PROMPT)


# ==================== 统一对外接口 ====================

async def chat_stream(
    messages: list[dict],
    kb_id: str | None = None,
    config: RAGConfig | None = None,
    stream: bool = True,
    show_reasoning: bool = False,
    uploaded_files: list[dict] | None = None,
):
    """Agent 对话（流式 / 非流式输出），完全兼容旧版 chat_chain.chat_stream()。

    Args:
        uploaded_files: [{token, filename}] 用户上传的文件，Agent 自动导入沙盒

    Agent 自主决定：
    - 何时检索知识库
    - 何时联网搜索
    - 何时直接回答

    Yields:
        字典序列：
        - {"type": "tool_start", "tool": "search_web", "input": "..."}
        - {"type": "tool_end", "tool": "search_web", "output": "..."}
        - {"type": "reasoning", "token": "..."}       (仅 show_reasoning=True)
        - {"type": "token", "token": "..."}
        - {"type": "done"}
    """
    config = config or RAGConfig.from_json()

    # 将 kb_id 和 config 注入工具上下文
    set_agent_context(kb_id, config)

    # 启动 Docker 沙盒（对话期间持久存在）
    from server.agent.sandbox import create as create_sandbox, destroy as destroy_sandbox
    create_sandbox()

    # 将用户上传的文件导入沙盒
    uploaded_info = ""
    if uploaded_files:
        from server.agent.sandbox import get as get_sandbox
        sb = get_sandbox()
        parts = []
        for f in uploaded_files:
            host_path = f"uploads/{f['token']}/{f['filename']}"
            dest = sb.import_file(host_path) if sb else None
            if dest:
                parts.append(f"- {f['filename']} → {dest}")
            else:
                parts.append(f"- {f['filename']} → 导入失败")
        if parts:
            uploaded_info = "(系统提示：用户本次上传了以下文件，已导入沙盒，可直接处理。)\n" + "\n".join(parts)

    try:
        # 构建 LangChain 消息列表
        lc_messages = _build_messages(messages, uploaded_info)

        if not stream:
            graph = _build_graph()
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config={"recursion_limit": 50},
            )
            final = result["messages"][-1]
            yield {"type": "token", "token": str(final.content)}
            yield {"type": "done"}
            return

        async for event in _stream_agent(lc_messages, show_reasoning):
            yield event
    finally:
        destroy_sandbox()


# ==================== 内部实现 ====================

def _build_messages(raw_messages: list[dict], uploaded_info: str = "") -> list:
    """将前端消息列表转为 LangChain 消息对象。

    如果有上传文件，会将文件信息附加到最后一条用户消息中。
    """
    # 系统提示词 + 当前时间
    messages = [SystemMessage(content=_SYSTEM_PROMPT + _get_time_prompt())]

    for i, msg in enumerate(raw_messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # 将文件信息附加到最后一条用户消息
        if role == "user" and uploaded_info and i == len(raw_messages) - 1:
            content = f"{content}\n\n{uploaded_info}"
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))

    return messages


async def _stream_agent(messages: list, show_reasoning: bool):
    """流式执行 Agent，逐 token / 工具事件输出。"""
    graph = _build_graph()

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": 50},
        ):
            event_type = event.get("event", "")

            # -- LLM 流式输出的 token --
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                content = str(chunk.content) if hasattr(chunk, "content") and chunk.content else ""

                # 推理过程（DeepSeek reasoner）
                if show_reasoning:
                    reasoning = str(
                        getattr(chunk, "additional_kwargs", {}).get("reasoning_content", "")
                    )
                    if reasoning:
                        yield {"type": "reasoning", "token": reasoning}

                if content:
                    yield {"type": "token", "token": content}
                    await asyncio.sleep(0)

            # -- 工具调用开始 --
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", "")
                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "input": str(tool_input),
                }

            # -- 工具调用结束 --
            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                output = event.get("data", {}).get("output", "")

                # ToolMessage 的 output 可能是 ToolMessage 对象
                if hasattr(output, "content"):
                    output = str(output.content)

                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": str(output)[:500],  # 截断过长输出
                }

    except Exception as exc:
        yield {"type": "token", "token": f"\n\n（Agent 出错: {exc}）"}

    yield {"type": "done"}
