"""Skills 技能加载器。

Skills 是可扩展的指令集，每个 skill 是一个 Markdown 文件，
包含特定场景的工作流程和注意事项。

按需加载模式：
1. 系统提示词只注入技能摘要（名称 + 一句话描述）
2. Agent 需要时调用 load_skill 工具拉取完整内容
3. 这样不用的技能不占 token

Skill .md 文件格式（含 frontmatter）:

    ---
    name: data_analysis
    description: 数据分析、统计计算、生成图表
    keywords: [分析, 图表, 统计, CSV, pandas, matplotlib]
    ---

    # 技能正文...

如果没有 frontmatter，自动从标题和首行生成摘要。

配置格式（data/user_settings.json）:
    "skills": ["data_analysis", "web_scraping"]
"""

import re
from pathlib import Path

from server.logging_config import get_logger

_SKILLS_DIR = Path("skills")
logger = get_logger(__name__)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (metadata, body)。

    如果没有 frontmatter，返回 ({}, content)。
    """
    if not content.startswith("---"):
        return {}, content

    # 找第二个 --- 作为 frontmatter 结束
    parts = content[3:].split("---", 1)
    if len(parts) != 2:
        return {}, content

    raw_yaml = parts[0].strip()
    body = parts[1].strip()

    # 简易 YAML 解析（不引入 pyyaml 依赖）
    meta = {}
    for line in raw_yaml.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # 解析列表格式 [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                items = [
                    item.strip().strip("\"'")
                    for item in val[1:-1].split(",")
                    if item.strip()
                ]
                meta[key] = items
            else:
                meta[key] = val.strip("\"'")

    return meta, body


def load_skills_summary(skill_names: list[str]) -> str:
    """生成技能摘要段落，注入系统提示词。

    只包含每个技能的名称和一句话描述，不包含完整正文。
    Agent 需要详细指导时通过 load_skill 工具按需获取。

    Returns:
        摘要段落文本（空字符串表示无技能）
    """
    if not skill_names:
        return ""

    lines = []
    for name in skill_names:
        skill_path = _SKILLS_DIR / f"{name}.md"
        if not skill_path.exists():
            logger.warning("技能不存在: %s", name)
            continue

        content = skill_path.read_text(encoding="utf-8").strip()
        meta, body = _parse_frontmatter(content)

        # 摘要：优先用 frontmatter 的 description，否则取正文第一段
        desc = meta.get("description", "")
        if not desc:
            # 取正文第一个非标题行的非空行
            for line in body.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("```"):
                    desc = line
                    break
        if not desc:
            desc = "（无描述）"

        lines.append(f"- **{name}** — {desc}")
        logger.info("技能摘要已生成: %s", name)

    if not lines:
        return ""

    return (
        "\n\n## 已启用技能\n\n"
        "以下技能可根据用户任务参考使用。需要详细指导时，"
        "调用 `load_skill` 工具获取完整内容：\n\n"
        + "\n".join(lines)
    )


def load_skill_detail(skill_name: str) -> str:
    """加载单个技能的完整内容（供 load_skill 工具调用）。

    Args:
        skill_name: 技能名（不含 .md 扩展名）

    Returns:
        技能完整正文（frontmatter 之后的全部内容）。
        技能不存在时返回错误提示。
    """
    skill_path = _SKILLS_DIR / f"{skill_name}.md"
    if not skill_path.exists():
        available = list_available_skills()
        return (
            f"技能 '{skill_name}' 不存在。"
            f"可用技能: {', '.join(available) or '无'}"
        )

    content = skill_path.read_text(encoding="utf-8").strip()
    _, body = _parse_frontmatter(content)

    logger.info("技能详情已加载: %s (%d 字符)", skill_name, len(body))
    return body


def list_available_skills() -> list[str]:
    """列出 skills/ 目录下所有可用的技能名。"""
    if not _SKILLS_DIR.exists():
        return []
    return [f.stem for f in _SKILLS_DIR.glob("*.md")]


# ==================== 向后兼容 ====================
# 保留旧接口供其他模块引用（返回摘要而非全文）

def load_skills(skill_names: list[str]) -> str:
    """[已废弃] 请用 load_skills_summary()。"""
    return load_skills_summary(skill_names)
