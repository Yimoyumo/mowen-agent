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
# 用户级技能目录（npx skills add -g 全局安装位置）
_USER_SKILLS_DIR = Path.home() / ".agents" / "skills"
# 项目级技能目录（npx skills add 默认安装位置）
_PROJECT_AGENTS_DIR = Path.cwd() / ".agents" / "skills"
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


def _resolve_skill_path(name: str) -> Path | None:
    """解析技能路径，支持单文件和文件夹两种格式。

    搜索顺序（项目目录优先）：
    1. skills/{name}.md（项目单文件）
    2. skills/{name}/index.md（项目文件夹）
    3. .agents/skills/{name}/SKILL.md（npx skills 项目级安装）
    4. ~/.agents/skills/{name}/SKILL.md（npx skills 用户级安装）

    Returns:
        技能主文件路径，不存在返回 None。
    """
    # 1. 项目目录：单文件
    single = _SKILLS_DIR / f"{name}.md"
    if single.is_file():
        return single

    # 2. 项目目录：文件夹
    skill_dir = _SKILLS_DIR / name
    if skill_dir.is_dir():
        index = skill_dir / "index.md"
        if index.is_file():
            return index
        for md in sorted(skill_dir.glob("*.md")):
            return md

    # 3. 项目级 .agents/skills/（npx skills add 默认安装位置）
    if _PROJECT_AGENTS_DIR.exists():
        d = _PROJECT_AGENTS_DIR / name
        if d.is_dir():
            skill_md = d / "SKILL.md"
            if skill_md.is_file():
                return skill_md
            index = d / "index.md"
            if index.is_file():
                return index
            for md in sorted(d.glob("*.md")):
                return md

    # 4. 用户级 ~/.agents/skills/（npx skills add -g 安装位置）
    if _USER_SKILLS_DIR.exists():
        user_skill_dir = _USER_SKILLS_DIR / name
        if user_skill_dir.is_dir():
            skill_md = user_skill_dir / "SKILL.md"
            if skill_md.is_file():
                return skill_md
            index = user_skill_dir / "index.md"
            if index.is_file():
                return index
            for md in sorted(user_skill_dir.glob("*.md")):
                return md

        user_single = _USER_SKILLS_DIR / f"{name}.md"
        if user_single.is_file():
            return user_single

    return None


def load_skills_summary(skill_names: list[str]) -> str:
    """生成技能摘要段落，注入系统提示词。

    支持单文件（name.md）和文件夹（name/index.md）两种格式。
    摘要来自 frontmatter 的 description 字段。

    Returns:
        摘要段落文本（空字符串表示无技能）
    """
    if not skill_names:
        return ""

    lines = []
    for name in skill_names:
        skill_path = _resolve_skill_path(name)
        if not skill_path:
            logger.warning("技能不存在: %s", name)
            continue

        content = skill_path.read_text(encoding="utf-8").strip()
        meta, body = _parse_frontmatter(content)

        # 摘要：优先用 frontmatter 的 description，否则取正文第一段
        desc = meta.get("description", "")
        if not desc:
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

    支持两种格式：
    - 单文件：skills/{name}.md → 返回该文件正文
    - 文件夹：skills/{name}/ → 拼接目录下所有 .md 文件正文

    Args:
        skill_name: 技能名

    Returns:
        技能完整正文。技能不存在时返回错误提示。
    """
    skill_path = _resolve_skill_path(skill_name)
    if not skill_path:
        available = list_available_skills()
        return (
            f"技能 '{skill_name}' 不存在。"
            f"可用技能: {', '.join(available) or '无'}"
        )

    # 判断是单文件还是文件夹
    # 文件夹：技能文件在 {name}/ 子目录中（index.md / SKILL.md）
    is_folder = skill_path.parent.name == skill_name and skill_path.name in ("index.md", "SKILL.md")

    if not is_folder:
        # 单文件：直接返回正文
        content = skill_path.read_text(encoding="utf-8").strip()
        _, body = _parse_frontmatter(content)
        logger.info("技能详情已加载: %s (%d 字符)", skill_name, len(body))
        return body

    # 文件夹：拼接所有 .md 文件
    skill_dir = skill_path.parent
    parts = []
    for md_file in sorted(skill_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8").strip()
        _, body = _parse_frontmatter(content)
        if md_file.name == "index.md":
            # index.md 放最前面
            parts.insert(0, body)
        else:
            # 其他文件按文件名排序，加标题分隔
            title = md_file.stem.replace("_", " ").title()
            parts.append(f"\n\n## {title}\n\n{body}")

    full = "\n\n".join(parts).strip()
    logger.info("技能详情已加载: %s (%d 字符, %d 个文件)",
                skill_name, len(full), len(parts))
    return full


def list_available_skills() -> list[str]:
    """列出所有可用技能名（扫描三个目录）。

    搜索位置：
    - skills/*.md 和 skills/*/（项目 skills 目录）
    - .agents/skills/*/（npx skills add 项目级安装位置）
    - ~/.agents/skills/*/ 和 ~/.agents/skills/*.md（用户级安装位置）
    """
    names = set()

    # 项目 skills/ 目录
    if _SKILLS_DIR.exists():
        for f in _SKILLS_DIR.glob("*.md"):
            names.add(f.stem)
        for d in _SKILLS_DIR.iterdir():
            if d.is_dir() and any(d.glob("*.md")):
                names.add(d.name)

    # 项目 .agents/skills/ 目录
    if _PROJECT_AGENTS_DIR.exists():
        for d in _PROJECT_AGENTS_DIR.iterdir():
            if d.is_dir() and any(d.glob("*.md")):
                names.add(d.name)

    # 用户 ~/.agents/skills/ 目录
    if _USER_SKILLS_DIR.exists():
        for d in _USER_SKILLS_DIR.iterdir():
            if d.is_dir() and any(d.glob("*.md")):
                names.add(d.name)
        for f in _USER_SKILLS_DIR.glob("*.md"):
            names.add(f.stem)

    return sorted(names)


# ==================== 向后兼容 ====================
# 保留旧接口供其他模块引用（返回摘要而非全文）

def load_skills(skill_names: list[str]) -> str:
    """[已废弃] 请用 load_skills_summary()。"""
    return load_skills_summary(skill_names)
