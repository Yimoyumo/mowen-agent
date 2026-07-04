"""RAG 问答入口脚本。

用法：
    python ask.py "问题内容"
"""

import sys

from rag.pipeline import ask


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ask.py '你的问题'")
        sys.exit(1)

    question = sys.argv[1]
    result = ask(question)

    print("\n=== 问题 ===")
    print(result["input"])
    print("\n=== 回答 ===")
    print(result["answer"])
    print("\n=== 参考上下文 ===")
    for i, doc in enumerate(result["context"], 1):
        print(f"[{i}] {doc.page_content[:200]}...")
