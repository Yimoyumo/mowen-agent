"""Pytest 全局夹具。"""

import os
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def tmp_settings_file(tmp_path: Path) -> Path:
    """创建临时 user_settings.json 路径。"""
    return tmp_path / "user_settings.json"


@pytest.fixture
def sample_novel_text() -> str:
    """示例小说文本，用于测试章节切分。"""
    return """第一章 伊始之日

清晨的阳光洒在小镇上，少女推开了家门。
她叫洛烟，是个普通的高中生。
今天是她转学的第一天。

第二章 命运的齿轮

转学后的第一周，洛烟就遇到了奇怪的事情。
学校旧校舍的走廊尽头，有一扇从未打开过的门。
"那扇门后面，什么都没有。"学长这样说。
但是洛烟总觉得不太对劲。

第三章 真相

门被打开了。里面是一间旧教室。
教室的桌椅排列整齐，黑板上还留着粉笔字。
"欢迎回来。"黑板上写着这几个字。
洛烟的心跳加速了。

终章 尾声

一切尘埃落定。
洛烟站在校门前，回头看了一眼旧校舍。
风轻轻吹过，带走了最后的秘密。
"""


@pytest.fixture
def sample_markdown_text() -> str:
    """示例 Markdown 文本，用于测试技术文档切分。"""
    return """# Python 入门指南

Python 是一门简单易学的编程语言。

## 安装

### Windows 安装

从官网下载安装包，双击运行即可。

### Linux 安装

使用包管理器安装：`apt install python3`

## 基础语法

### 变量

Python 是动态类型语言，变量不需要声明类型。

```python
x = 10
name = "Alice"
```

### 条件语句

使用 if-elif-else 结构：

```python
if x > 0:
    print("正数")
elif x < 0:
    print("负数")
else:
    print("零")
```
"""
