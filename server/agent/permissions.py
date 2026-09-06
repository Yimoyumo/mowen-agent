"""权限引擎：对 Agent 的命令 / 文件操作进行安全分类。

判定结果分为三档：
- AUTO: 自动放行（低风险，无需用户审批）
- ASK : 需要用户审批（人机交互 HITL 卡片）
- DENY: 直接拒绝（高危操作，禁止执行）

设计原则：
- classify_command / classify_file_op 为**纯函数**，不依赖全局状态，便于单测。
- 所有可配置项（deny_commands / auto_allow_commands / ask_commands）通过可选的
  config 参数传入（由调用方从 executor_config 读取），默认使用内置规则。
- approval_mode（auto / ask_dangerous / ask_all）的语义在调用方
  （见 apply_approval_mode()）统一处理，核心判别函数保持纯粹。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Decision(str, Enum):
    AUTO = "auto"
    ASK = "ask"
    DENY = "deny"


@dataclass
class Classification:
    """对一次操作的权限分类结果。"""

    decision: Decision
    reason: str = ""


# ==================== 内置规则表 ====================

# 1. 高危命令（deny 正则表，命中直接拒绝）
_DENY_PATTERNS: list[str] = [
    r"mkfs",                                    # 格式化设备
    r"shutdown\b|\breboot\b|\bpoweroff\b|\bhalt\b",  # 关机/重启
    r"\bdd\s+.*of=/dev/",                       # 写裸设备
    r":\(\)\s*\{.*\};\s*:",                     # fork 炸弹
    r"\bchmod\s+-R\s+777\s+/",                  # 递归放宽根目录权限
    r"\>\s*/dev/sd",                            # 写入磁盘设备
    r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba)?sh",  # 管道直接执行远程脚本
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)*(/|\s)",  # 根目录删除
]

# 2. 敏感路径（命令/路径包含时至少 ASK）
_SENSITIVE_PATTERNS: list[str] = [
    r"/etc/", r"/usr/", r"/bin/", r"/sbin/", r"/boot/", r"/sys/",
    r"/proc/", r"/dev/", r"/root/", r"/var/", r"/lib/", r"~/.ssh",
]

# 4. 命令首 token 自动放行表
_AUTO_ALLOW_TOKENS: list[str] = [
    "python", "python3", "ls", "cat", "head", "tail", "echo", "pwd",
    "mkdir", "touch", "wc", "tree", "which", "date", "stat", "file",
    "grep", "du", "sort", "uniq", "diff", "basename", "dirname", "env",
    "id", "uname",
]

# 4. 命令首 token 需审批表
_ASK_TOKENS: list[str] = [
    "rm", "cp", "mv", "curl", "wget", "pip", "pip3", "apt", "apt-get",
    "npm", "npx", "chmod", "chown", "ssh", "scp", "tar", "unzip",
]

# 4. 子命令白名单：命中则 AUTO，否则 ASK
_SUBCOMMAND_AUTO: dict[str, set[str]] = {
    "git": {"status", "log", "diff", "show", "branch", "add", "commit"},
    "pip": {"list", "show", "freeze"},
    "npm": {"list", "ls"},
    "apt": {"list", "search", "show"},
}

# find 的预定义子命令权限：默认 AUTO，仅当含 -delete/-exec 时降级为 ASK
_FIND_DANGEROUS_FLAGS = ("-delete", "-exec")

# 包装器命令：段首命中即至少 ASK（bash/sh 仅当带 -c 才算包装器，纯 `bash script.sh` 走原分类）
_WRAPPER_TOKENS = {
    "sudo", "env", "xargs", "eval", "exec", "nohup", "setsid", "stdbuf", "timeout",
}

# shell 控制操作符：复合命令据此切分（引号感知）
_OP = (";", "&&", "||", "|", "&", "\n")


# ==================== 工具函数 ====================

def _first_token(command: str) -> str:
    """提取命令的首个 token（小写）。

    处理 sudo / env 前缀？不处理，保持简单：直接取第一个空白分隔的词。
    命令最前面的空白会被 strip。
    """
    stripped = command.strip()
    if not stripped:
        return ""
    # 去掉可能的行尾注释，仅取第一个词
    m = re.match(r"([^\s|;&]+)", stripped)
    return m.group(1).lower() if m else ""


def _split_command_segments(command: str) -> list[str]:
    """按 shell 控制操作符把命令切分为子段（引号感知）。

    遍历字符，跟踪单/双引号状态；在引号外的 `;` `&&` `||` `|` `&` `换行` 处切分。
    引号内的分隔符不会被误切。

    Returns:
        子段列表（未 strip，调用方自行 strip 并跳过空段）。
    """
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
        elif c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
        elif not in_single and not in_double:
            # 先匹配双字符操作符
            if c == "&" and i + 1 < n and command[i + 1] == "&":
                segments.append("".join(current)); current = []; i += 2; continue
            if c == "|" and i + 1 < n and command[i + 1] == "|":
                segments.append("".join(current)); current = []; i += 2; continue
            if c in _OP:
                segments.append("".join(current)); current = []; i += 1; continue
            current.append(c)
        else:
            current.append(c)
        i += 1
    segments.append("".join(current))
    return segments


def _classify_segment(segment: str, auto_tokens: list[str], ask_tokens: list[str]) -> Classification:
    """对单个子段进行分类（敏感路径 → 包装器 → 首 token 分类）。"""
    seg = segment.strip()
    if not seg:
        return Classification(Decision.AUTO, "空段")

    # 敏感路径 → 至少 ASK
    hit = _matches_any(_SENSITIVE_PATTERNS, seg)
    if hit:
        return Classification(Decision.ASK, f"涉敏感路径 {hit}，需审批")

    # 包装器命令 → 至少 ASK（bash/sh 仅当带 -c）
    token = _first_token(seg)
    is_wrapper = token in _WRAPPER_TOKENS
    if token in ("bash", "sh") and "-c" not in seg:
        is_wrapper = False
    if is_wrapper:
        return Classification(Decision.ASK, f"命令 {token} 为包装器，需审批")

    # 命令首 token 分类
    decision, reason = _classify_first_token(seg, auto_tokens, ask_tokens)
    return Classification(decision, reason)


def _matches_any(patterns: list[str], text: str) -> str | None:
    """返回首个命中的正则模式；无命中返回 None。"""
    for pat in patterns:
        if re.search(pat, text):
            return pat
    return None


def _classify_first_token(command: str, auto_tokens: list[str], ask_tokens: list[str]) -> tuple[Decision, str]:
    """基于命令首 token 及子命令白名单分类。"""
    token = _first_token(command)
    if not token:
        return Decision.ASK, "空命令，默认需审批"

    # find 特殊处理：仅当含危险 flag 才 ASK
    if token == "find":
        if any(flag in command for flag in _FIND_DANGEROUS_FLAGS):
            return Decision.ASK, "find 含 -delete/-exec 等危险操作，需审批"
        return Decision.AUTO, "find 只读操作，自动放行"

    if token in auto_tokens:
        return Decision.AUTO, f"命令 {token} 在自动放行列表"

    # 子命令白名单判断（对 git/pip/npm/apt 等，在 ask 判断之前，避免被 ask token 拦截）
    sub_auto = _SUBCOMMAND_AUTO.get(token)
    if sub_auto is not None:
        # 提取第二个 token 作为子命令
        parts = command.strip().split()
        sub = parts[1].lower() if len(parts) > 1 else ""
        if sub in sub_auto:
            return Decision.AUTO, f"{token} {sub} 在白名单内"
        return Decision.ASK, f"{token} 的 {sub or '? '}子命令不在白名单，需审批"

    if token in ask_tokens:
        return Decision.ASK, f"命令 {token} 在需审批列表"

    # 都不命中 → 未知命令，默认需审批
    return Decision.ASK, f"未知命令 {token}，默认需审批"


# ==================== 对外分类函数 ====================

def classify_command(
    command: str,
    workspace: Path,
    config: dict | None = None,
) -> Classification:
    """对 shell 命令进行安全分类。

    Args:
        command: 用户/Agent 要执行的命令
        workspace: 会话工作区根目录（用于路径信任根判断）
        config: 执行器配置（executor_config），可含
            deny_commands / auto_allow_commands / ask_commands，追加合并内置规则。
            不传则仅用内置规则。

    Returns:
        Classification（decision + reason）。
    """
    config = config or {}
    deny_extra = config.get("deny_commands") or []
    auto_extra = config.get("auto_allow_commands") or []
    ask_extra = config.get("ask_commands") or []

    deny_list = [*_DENY_PATTERNS, *[str(p) for p in deny_extra]]
    auto_tokens = [*_AUTO_ALLOW_TOKENS, *[str(t).lower() for t in auto_extra]]
    ask_tokens = [*_ASK_TOKENS, *[str(t).lower() for t in ask_extra]]

    # 1. DENY：高危命令（对整条命令先行匹配，保持现状）
    hit = _matches_any(deny_list, command)
    if hit:
        return Classification(Decision.DENY, f"高危命令被拒绝（{hit}）")

    # 2. 按 shell 控制操作符切分子段，逐段分类，整体取最严者（DENY > ASK > AUTO）
    worst = Decision.AUTO
    reasons: list[str] = []
    for seg in _split_command_segments(command):
        cls = _classify_segment(seg, auto_tokens, ask_tokens)
        if cls.decision == Decision.DENY:
            return cls
        if cls.decision == Decision.ASK:
            worst = Decision.ASK
            reasons.append(cls.reason)
    if worst == Decision.ASK:
        return Classification(Decision.ASK, "; ".join(reasons) or "复合命令含需审批子命令")
    return Classification(Decision.AUTO, "命令各子段均为自动放行")


def classify_file_op(
    op: str,
    path: str,
    workspace: Path,
    config: dict | None = None,
) -> Classification:
    """对文件操作（read/write/list/export）进行安全分类。

    Args:
        op: 操作类型 read / write / list / export
        path: 目标路径
        workspace: 会话工作区根目录
        config: 执行器配置（可选，含 deny_commands）

    Returns:
        Classification（decision + reason）。
    """
    config = config or {}

    # 1. DENY：敏感路径高危写操作
    deny_list = [*_DENY_PATTERNS, *[str(p) for p in (config.get("deny_commands") or [])]]
    hit = _matches_any(deny_list, str(path))
    if hit:
        return Classification(Decision.DENY, f"文件操作命中危险规则（{hit}），已拒绝")

    # 2. 敏感路径 → 至少 ASK
    hit = _matches_any(_SENSITIVE_PATTERNS, str(path))
    if hit:
        return Classification(Decision.ASK, f"涉敏感路径 {hit}，需审批")

    # 3. 文件操作信任根：位于 workspace / uploads / downloads 内 → AUTO
    if workspace is not None:
        try:
            target = Path(path)
            if not target.is_absolute():
                target = workspace / target
            target = target.resolve()
            ws_root = workspace.resolve()
            trust_roots = [
                ws_root,
                (Path.cwd() / "uploads").resolve(),
                (Path.cwd() / "downloads").resolve(),
            ]
            for root in trust_roots:
                if target == root or root in target.parents:
                    return Classification(Decision.AUTO, f"文件操作位于信任根（{op}）")
        except OSError:
            pass
    else:
        # workspace 为空时退化为宽松处理
        return Classification(Decision.AUTO, "无工作区约束，按信任根放宽")

    # 不在信任根 → ASK
    return Classification(Decision.ASK, f"文件操作路径 {path} 不在信任根内，需审批")


def apply_approval_mode(cls: Classification, approval_mode: str) -> Classification:
    """按 approval_mode 调整分类结果。

    语义（在调用方统一处理，classify_* 保持纯函数）：
    - approval_mode == "auto"：除 DENY 外一律放行为 AUTO（不弹审批卡片）。
    - approval_mode == "ask_all"：除 DENY 外一律需审批为 ASK。
    - 其他（默认 ask_dangerous，含未配置）：保持 classify 原始结果。

    Args:
        cls: 原始分类结果
        approval_mode: "auto" / "ask_all" / "ask_dangerous" / 未配置

    Returns:
        调整后的分类结果（DENY 始终不可被覆盖）。
    """
    if cls.decision == Decision.DENY:
        return cls
    if approval_mode == "auto":
        return Classification(Decision.AUTO, f"auto 模式自动放行（原：{cls.reason}）")
    if approval_mode == "ask_all":
        return Classification(Decision.ASK, f"ask_all 模式需审批（原：{cls.reason}）")
    return cls
