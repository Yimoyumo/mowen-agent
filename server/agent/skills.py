"""Skills 技能加载器。

Skills 是可扩展的指令集，每个 skill 是一个 Markdown 文件，
包含特定场景的工作流程和注意事项。
Agent 在系统提示词中根据用户任务自动参考相关技能。

支持两种形式：
1. 指令式（.md）：纯提示词指导，无额外工具
2. 代码式（.py）：提供额外的 Python 工具函数

配置格式（data/user_settings.json）:
    "skills": ["data_analysis", "web_scraping"]
"""

from pathlib import Path

from server.logging_config import get_logger

_SKILLS_DIR = Path("skills")
logger = get_logger(__name__)


def load_skills(skill_names: list[str]) -> str:
    """加载指定技能的提示词，拼接到系统提示词。

    Args:
        skill_names: 技能名列表（对应 skills/ 目录下的 .md 文件名，不含扩展名）

    Returns:
        拼接好的技能提示词文本（空字符串表示无技能）
    """
    if not skill_names:
        return ""

    parts = []
    for name in skill_names:
        skill_path = _SKILLS_DIR / f"{name}.md"
        if not skill_path.exists():
            logger.warning("技能不存在: %s", name)
            continue

        content = skill_path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### 技能：{name}\n\n{content}")
            logger.info("已加载技能: %s", name)

    if not parts:
        return ""

    return "\n\n## 已启用技能\n\n以下技能可根据用户任务参考使用：\n\n" + "\n\n---\n\n".join(parts)


def list_available_skills() -> list[str]:
    """列出 skills/ 目录下所有可用的技能名。"""
    if not _SKILLS_DIR.exists():
        return []
    return [f.stem for f in _SKILLS_DIR.glob("*.md")]
