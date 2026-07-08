"""记忆系统模块。

提供基于 JSON 文件的轻量记忆存储，支持：
- 自动提取：对话结束后 LLM 分析，提取值得记住的信息
- 延迟合并：300 秒内无新消息才提取，长对话只提取一次
- 已知记忆：提取时告知 LLM 已有记忆，避免重复提取
- 自动去重：关键词重叠 >70% 视为重复，更新而非新增
- 自动淘汰：超过 100 条时删除最不活跃的
- 全量注入：记忆 <100 条时全量注入 system prompt

数据文件：
- data/memories.json   — 长期记忆（事实/偏好/摘要）
- data/user_profile.json — 用户画像（技能/兴趣/偏好）

用法：
    from server.agent.memory import memory_store

    # 对话前：注入记忆到 prompt
    prompt_section = memory_store.get_prompt()

    # 对话后：调度延迟提取
    memory_store.schedule_extraction(messages)

    # 手动管理
    memory_store.add("fact", "用户擅长 Python")
    memory_store.get_all()
    memory_store.delete("mem_001")
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from server.core.config import RAGConfig
from server.core.logging_config import get_logger

logger = get_logger(__name__)

# ==================== 常量 ====================

_DATA_DIR = Path("data")
_MEMORIES_FILE = _DATA_DIR / "memories.json"
_PROFILE_FILE = _DATA_DIR / "user_profile.json"

_MAX_MEMORIES = 100          # 记忆上限
_DEDUP_THRESHOLD = 0.3        # 关键词重叠超过此值视为重复
_EXTRACTION_DELAY = 300      # 300 秒无新消息 → 视为会话结束
_MAX_EXTRACTIONS = 3         # 每次最多提取 3 条
_MIN_MESSAGES = 8            # 至少 8 条消息（4 轮）才提取
_MIN_USER_MSG_LEN = 10       # 用户最后一条消息至少 10 字才提取


# ==================== 记忆提取 Prompt ====================

_EXTRACTION_SYSTEM = """你是一个记忆提取助手。分析对话，提取需要长期记住的重要信息。"""

_EXTRACTION_PROMPT = """分析以下对话，提取需要长期记住的重要信息。

只提取以下类型：
1. fact — 用户的身份、职业、技能水平、正在做的项目
2. preference — 用户的明确偏好（回答风格、工具选择等）
3. summary — 对话的核心结论（仅当有重要决策时）

输出 JSON 数组：
[{{"type": "fact", "content": "用户是后端开发者，擅长 Python"}}]

规则：
- 跳过临时闲聊和一次性操作细节（如"帮我算个加法"）
- 每条记忆是一个完整、可独立理解的句子
- 没有值得记住的信息时返回 []
- 最多提取 {max_extract} 条，宁缺毋滥
- 不要重复已有记忆的内容

已有记忆：
{existing_memories}

对话内容：
{conversation}
"""


# ==================== 记忆存储 ====================

class MemoryStore:
    """记忆存储管理器。

    线程安全通过文件锁保证（与 knowledge_base.py 相同模式）。
    延迟提取通过 asyncio.Task 实现，300 秒内无新消息才真正执行。
    """

    def __init__(self):
        self._extraction_timer: asyncio.Task | None = None
        self._pending_messages: list[dict] | None = None  # 最后一次调度的消息快照

    # ---- 读写 ----

    def load(self) -> list[dict]:
        """加载所有记忆。"""
        import fcntl

        if not _MEMORIES_FILE.exists():
            return []

        lock_path = _MEMORIES_FILE.with_suffix(".lock")
        _DATA_DIR.mkdir(parents=True, exist_ok=True)

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                with open(_MEMORIES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        return data.get("memories", [])

    def save(self, memories: list[dict]) -> None:
        """保存所有记忆（原子写入 + 文件锁）。"""
        import fcntl

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = _MEMORIES_FILE.with_suffix(".lock")
        tmp_path = _MEMORIES_FILE.with_suffix(".tmp")

        data = {
            "memories": memories,
            "updated_at": datetime.now().isoformat(),
        }

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(str(tmp_path), str(_MEMORIES_FILE))
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    # ---- 增删改查 ----

    def add(self, type: str, content: str) -> str | None:
        """添加一条记忆，自动去重和淘汰。

        Args:
            type: fact / preference / summary
            content: 记忆内容

        Returns:
            新记忆的 ID，如果因重复未新增则返回 None
        """
        memories = self.load()

        # 去重检查
        for existing in memories:
            if self._similarity(content, existing["content"]) > _DEDUP_THRESHOLD:
                # 重复 → 更新为更完整的版本
                if len(content) > len(existing["content"]):
                    existing["content"] = content
                    self.save(memories)
                    logger.debug("记忆更新（去重）: %s", content[:50])
                return None

        # 新增
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        memories.append({
            "id": mem_id,
            "type": type,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "hit_count": 0,
            "last_used": None,
        })

        # 淘汰
        if len(memories) > _MAX_MEMORIES:
            memories.sort(key=lambda m: (m.get("hit_count", 0), m.get("last_used") or ""))
            removed = memories.pop(0)
            logger.info("记忆淘汰: %s", removed.get("content", "")[:50])

        self.save(memories)
        logger.info("记忆新增 [%s]: %s", type, content[:50])
        return mem_id

    def get_all(self) -> list[dict]:
        """获取所有记忆。"""
        return self.load()

    def delete(self, mem_id: str) -> bool:
        """删除指定记忆。"""
        memories = self.load()
        before = len(memories)
        memories = [m for m in memories if m["id"] != mem_id]
        if len(memories) < before:
            self.save(memories)
            return True
        return False

    def clear(self) -> None:
        """清空所有记忆。"""
        self.save([])

    # ---- 注入 prompt ----

    def get_prompt(self) -> str:
        """生成注入 system prompt 的记忆段落。

        全量注入（记忆 <100 条时不需要检索）。
        """
        memories = self.load()
        if not memories:
            return ""

        facts = [m for m in memories if m["type"] == "fact"]
        prefs = [m for m in memories if m["type"] == "preference"]
        summaries = [m for m in memories if m["type"] == "summary"]

        sections = []

        if facts or prefs:
            lines = []
            for m in facts:
                lines.append(f"- {m['content']}")
            for m in prefs:
                lines.append(f"- {m['content']}")
            sections.append("你对用户的了解：\n" + "\n".join(lines))

        if summaries:
            lines = [f"- {m['content']}" for m in summaries[-5:]]  # 最近的 5 条摘要
            sections.append("近期对话摘要：\n" + "\n".join(lines))

        if not sections:
            return ""

        return "\n\n## 关于用户\n\n" + "\n\n".join(sections)

    # ---- 延迟提取 ----

    def schedule_extraction(self, messages: list[dict]) -> None:
        """调度延迟提取：300 秒内无新消息才执行。

        如果在 300 秒内又来了新消息，取消上一个定时器，重新计时。
        效果：长对话只提取一次（最后一次的完整上下文）。

        必须在 async 上下文中调用（chat_stream 是 async generator）。
        如果在同步上下文中调用（如测试），跳过调度。
        """
        # 条件检查（带日志，方便定位为什么没触发）
        if len(messages) < _MIN_MESSAGES:
            logger.info("记忆提取跳过：消息数 %d < %d", len(messages), _MIN_MESSAGES)
            return

        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        if len(last_user.strip()) < _MIN_USER_MSG_LEN:
            logger.info("记忆提取跳过：最后一条用户消息太短 (%d 字)", len(last_user.strip()))
            return

        # 检查是否有运行中的事件循环
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.info("记忆提取跳过：无运行中的事件循环")
            return

        # 取消上一个定时器
        if self._extraction_timer and not self._extraction_timer.done():
            self._extraction_timer.cancel()

        # 启动新的
        # 保存 messages 的快照（避免后续修改影响）
        messages_snapshot = [dict(m) for m in messages]
        self._pending_messages = messages_snapshot  # 保存快照，供 flush 用
        self._extraction_timer = asyncio.create_task(
            self._delayed_extract(messages_snapshot)
        )
        logger.info("记忆提取已调度，%ds 后执行（消息数=%d）", _EXTRACTION_DELAY, len(messages))

    async def flush_pending_extraction(self) -> int:
        """立即执行待处理的记忆提取（跳过延迟等待）。

        用于服务关闭时（如 --reload 重启），防止延迟任务被取消而丢失。
        如果没有 pending 任务则跳过。
        """
        # 取消延迟任务
        if self._extraction_timer and not self._extraction_timer.done():
            self._extraction_timer.cancel()
            try:
                await self._extraction_timer
            except asyncio.CancelledError:
                pass
            self._extraction_timer = None

        # 立即提取
        if self._pending_messages:
            messages = self._pending_messages
            self._pending_messages = None
            logger.info("记忆提取：立即执行（服务关闭触发，消息数=%d）", len(messages))
            try:
                # 加 30 秒超时保护，防止 shutdown 时事件循环即将关闭导致卡死
                return await asyncio.wait_for(
                    self._extract_memories(messages),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("记忆提取：flush 超时（30s），放弃")
                return 0
            except Exception as exc:
                logger.warning("记忆提取：flush 失败: %s", exc, exc_info=True)
                return 0
        else:
            logger.info("记忆提取：无 pending 消息，跳过 flush")
        return 0

    async def _delayed_extract(self, messages: list[dict]) -> None:
        """延迟提取：等待 300 秒，未被取消才真正执行。"""
        try:
            await asyncio.sleep(_EXTRACTION_DELAY)
            logger.info("记忆提取：延迟到期，开始执行")
            await self._extract_memories(messages)
        except asyncio.CancelledError:
            logger.info("记忆提取已取消（用户又发新消息了）")
            raise

    async def _extract_memories(self, messages: list[dict]) -> int:
        """用 LLM 分析对话，提取记忆。

        Returns:
            新增记忆条数
        """
        from server.llm.factory import get_chat_model
        try:
            config = RAGConfig.from_settings()
            llm = get_chat_model(config)
        except Exception as exc:
            logger.warning("记忆提取失败：LLM 初始化失败: %s", exc, exc_info=True)
            return 0

        # 格式化对话
        conversation = self._format_conversation(messages)
        logger.info("记忆提取：开始调用 LLM（对话 %d 字符）", len(conversation))

        # 加载已有记忆，让 LLM 避免重复提取
        existing = self.load()
        existing_text = "\n".join(f"- [{m['type']}] {m['content']}" for m in existing) or "（暂无记忆）"

        try:
            response = await llm.ainvoke([
                SystemMessage(content=_EXTRACTION_SYSTEM),
                HumanMessage(content=_EXTRACTION_PROMPT.format(
                    max_extract=_MAX_EXTRACTIONS,
                    conversation=conversation,
                    existing_memories=existing_text,
                )),
            ])
        except Exception as exc:
            logger.warning("记忆提取 LLM 调用失败: %s", exc, exc_info=True)
            return 0

        logger.info("记忆提取：LLM 返回 %d 字符", len(str(response.content)))

        # 解析 JSON
        new_memories = self._parse_extraction(response.content)
        if not new_memories:
            logger.info("记忆提取完成：无新记忆")
            return 0

        # 添加（自动去重）
        added = 0
        for mem in new_memories[:_MAX_EXTRACTIONS]:
            mem_type = mem.get("type", "fact")
            content = mem.get("content", "").strip()
            if not content:
                continue
            if self.add(mem_type, content) is not None:
                added += 1

        logger.info("记忆提取完成：提取 %d 条，新增 %d 条", len(new_memories), added)
        return added

    # ---- 工具方法 ----

    def _format_conversation(self, messages: list[dict]) -> str:
        """格式化对话为文本。"""
        role_map = {"user": "用户", "assistant": "助手"}
        lines = []
        for m in messages[-20:]:  # 最多取最近 20 条，避免太长
            role = role_map.get(m.get("role", "user"), "用户")
            content = m.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _parse_extraction(self, text: str) -> list[dict]:
        """解析 LLM 输出的 JSON 数组。"""
        import re

        # 尝试提取 JSON 数组
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if not match:
            return []

        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError as exc:
            logger.warning("记忆提取 JSON 解析失败: %s text=%.100s", exc, match.group())

        return []

    def _similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的关键词重叠率（Jaccard 相似度）。

        Returns:
            0.0 ~ 1.0
        """
        # 简单分词：按标点和空格切分，取长度 >=2 的词
        import re

        def tokenize(text):
            tokens = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z_]{2,}|\d+', text.lower()))
            return tokens

        tokens1 = tokenize(text1)
        tokens2 = tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        return len(intersection) / len(union)


# ==================== 全局单例 ====================

memory_store = MemoryStore()
