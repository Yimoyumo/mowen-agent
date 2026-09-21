"""从 uv export 生成的 requirements 文件里整块剔除指定包。

为什么需要它：`uv export` 输出的每条依赖是**多行块**——首行不缩进
（`pkg==ver \\`），后面跟着缩进的 `--hash=` 续行与 `# via` 注释。
按行 grep 只会删掉首行，留下孤立的续行，`uv pip install -r` 会直接失败：

    error: Unexpected '-', expected '-c', '-e', '-r' or the start of a
    requirement at /tmp/req-app.txt:85:5

本脚本按"非缩进行 = 包首行"切块，整块删除，缩进的续行与注释跟随其首行
一起保留或删除；顶部以 `#` 开头的生成器注释不受影响。

用法：
    filter_requirements.py --exclude-regex 'notebook|ipykernel' 输入 输出

退出码：0 = 正常（即使有待剔除项不在文件中，也只打印提示）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 包首行形如 `name==1.2.3 \` 或 `name==1.2.3 ; python_version < "3.12" \`
_HEAD = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")


def _norm(name: str) -> str:
    return name.lower().replace("_", "-")


def filter_file(src: Path, dst: Path, exclude: re.Pattern[str]) -> tuple[set[str], set[str]]:
    kept: set[str] = set()
    dropped: set[str] = set()
    out: list[str] = []
    skipping = False

    for line in src.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not line[0].isspace():
            # 非缩进行：要么是包首行，要么是文件顶部的生成器注释
            m = _HEAD.match(line)
            if m:
                name = _norm(m.group(1))
                skipping = bool(exclude.fullmatch(name))
                (dropped if skipping else kept).add(name)
            else:
                skipping = False
        if not skipping:
            out.append(line)

    dst.write_text("".join(out), encoding="utf-8")
    return kept, dropped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="整块剔除 requirements 中的指定包")
    parser.add_argument("--exclude-regex", required=True, help="包名完全匹配的正则（如 a|b|c）")
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    args = parser.parse_args(argv[1:])

    exclude = re.compile(args.exclude_regex)
    kept, dropped = filter_file(args.src, args.dst, exclude)
    print(f"保留 {len(kept)} 个包，剔除 {len(dropped)} 个包 -> {args.dst}")

    missing = [n for n in exclude.pattern.split("|") if _norm(n) not in kept | dropped]
    if missing:
        # 只提示不报错：待剔除项不在文件里（依赖已变）不应让构建失败
        print(f"提示：{len(missing)} 个待剔除项不在输入文件中，已忽略")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
