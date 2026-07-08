---
name: document-conversion
description: 文档格式转换，支持 docx/pdf/xlsx/pptx/md/html 互转，保留格式
keywords: [转换, 文档, docx, pdf, xlsx, markdown, 格式, convert, 导出, pptx]
---

# 文档转换技能

## 适用场景

用户要求将文档从一种格式转换为另一种格式时激活。例如：docx 转 pdf、pdf 转 markdown、xlsx 转 csv、md 转 docx 等。

## 沙盒中已预装的库

以下 Python 库已预装在沙盒中，可直接 `import` 使用：

| 库 | 用途 |
|---|---|
| `python-docx` (`import docx`) | 读取/写入 .docx 文件 |
| `pypdf` | 读取 .pdf 文本 |
| `openpyxl` | 读取/写入 .xlsx 文件 |
| `markdown` | Markdown → HTML |
| `weasyprint` | HTML → PDF 渲染 |
| `PIL` / `Pillow` | 图片处理 |

## 标准工作流程

1. 确认源文件路径（用户上传的文件通常已在 /workspace 下）
2. 用 `sandbox_write_file` 写转换脚本
3. 用 `sandbox_run` 执行脚本
4. 用 `sandbox_export_file` 导出结果给用户

## 常用转换脚本模板

### docx → pdf（python-docx + weasyprint）

```python
import sys, base64
from docx import Document
from pathlib import Path

doc = Document("/workspace/input.docx")
parts = [
    "<html><head><meta charset='utf-8'><style>",
    "body{font-family:sans-serif;max-width:800px;margin:40px auto;line-height:1.8}",
    "h1,h2,h3{margin-top:20px}",
    "table{border-collapse:collapse;width:100%;margin:12px 0}",
    "td,th{border:1px solid #ccc;padding:6px 10px}",
    "pre{background:#f5f5f5;padding:10px;overflow-x:auto}",
    "img{max-width:100%}",
    "</style></head><body>"
]

for para in doc.paragraphs:
    style = para.style.name or ""
    text = para.text.strip()
    if not text:
        parts.append("<br/>")
        continue
    if style.startswith("Heading"):
        lv = int(style.replace("Heading ","").replace("Heading",""))
        parts.append(f"<h{min(lv,4)}>{text}</h{min(lv,4)}>")
    elif style == "Title":
        parts.append(f"<h1>{text}</h1>")
    else:
        parts.append(f"<p>{text}</p>")

for table in doc.tables:
    parts.append("<table>")
    for i, row in enumerate(table.rows):
        tag = "th" if i == 0 else "td"
        cells = "".join(f"<{tag}>{cell.text}</{tag}>" for cell in row.cells)
        parts.append(f"<tr>{cells}</tr>")
    parts.append("</table>")

# 提取内嵌图片
for rel in doc.part.rels.values():
    if "image" not in rel.reltype:
        continue
    img_data, ext = rel.target_part.blob, rel.target_part.ext
    if ext in ("png","jpg","jpeg","gif","webp"):
        b64 = base64.b64encode(img_data).decode()
        mime = "image/" + ("jpeg" if ext=="jpg" else ext)
        parts.append(f'<img src="data:{mime};base64,{b64}" style="max-width:100%"/>')

parts.append("</body></html>")
from weasyprint import HTML
HTML(string="\n".join(parts)).write_pdf("/workspace/output.pdf")
print("OK")
```

### docx → markdown

```python
from docx import Document
doc = Document("/workspace/input.docx")
lines = []
for p in doc.paragraphs:
    style, text = p.style.name or "", p.text.strip()
    if not text: lines.append(""); continue
    if style.startswith("Heading"):
        lv = int(style.replace("Heading ","").replace("Heading",""))
        lines.append("#"*lv + " " + text)
    elif style == "Title": lines.append("# " + text)
    else: lines.append(text)
for t in doc.tables:
    lines.append("")
    for i, row in enumerate(t.rows):
        cells = [c.text.strip() for c in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0: lines.append("|" + "|".join(["---"]*len(cells)) + "|")
    lines.append("")
Path("/workspace/output.md").write_text("\n".join(lines), encoding="utf-8")
print("OK")
```

### pdf → markdown

```python
from pypdf import PdfReader
reader = PdfReader("/workspace/input.pdf")
lines = []
for i, page in enumerate(reader.pages):
    text = page.extract_text()
    if text:
        lines.append(f"## 第 {i+1} 页\n")
        lines.append(text.strip())
        lines.append("")
Path("/workspace/output.md").write_text("\n".join(lines), encoding="utf-8")
print("OK")
```

### xlsx → csv（每 sheet 一个 csv）

```python
from openpyxl import load_workbook
import os, csv
wb = load_workbook("/workspace/input.xlsx")
base = os.path.splitext(os.path.basename("/workspace/input.xlsx"))[0]
for ws in wb.worksheets:
    fname = f"/workspace/{base}_{ws.title}.csv"
    with open(fname, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for row in ws.iter_rows(values_only=True): w.writerow(row)
    print(f"OK: {os.path.basename(fname)}")
```

### xlsx → HTML 表格

```python
from openpyxl import load_workbook
wb = load_workbook("/workspace/input.xlsx")
parts = ["<html><head><meta charset='utf-8'></head><body>"]
for ws in wb.worksheets:
    parts.append(f"<h2>{ws.title}</h2><table border='1'>")
    for row in ws.iter_rows(values_only=True):
        cells = "".join(f"<td>{str(c) if c is not None else ''}</td>" for c in row)
        parts.append(f"<tr>{cells}</tr>")
    parts.append("</table>")
parts.append("</body></html>")
Path("/workspace/output.html").write_text("\n".join(parts), encoding="utf-8")
print("OK")
```

### md → pdf（markdown → HTML → weasyprint）

```python
import markdown
text = Path("/workspace/input.md").read_text(encoding="utf-8")
html_body = markdown.markdown(text, extensions=["tables","fenced_code"])
html = f"""<html><head><meta charset='utf-8'>
<style>
body{{font-family:sans-serif;max-width:800px;margin:40px auto;line-height:1.8}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:8px}}
pre{{background:#f5f5f5;padding:12px}} code{{background:#f5f5f5;padding:2px 4px}}
</style></head><body>{html_body}</body></html>"""
from weasyprint import HTML
HTML(string=html).write_pdf("/workspace/output.pdf")
print("OK")
```

### md → docx

```python
from docx import Document
text = Path("/workspace/input.md").read_text(encoding="utf-8")
doc = Document()
for line in text.split("\n"):
    s = line.strip()
    if not s: continue
    if s.startswith("### "): doc.add_heading(s[4:], level=3)
    elif s.startswith("## "): doc.add_heading(s[3:], level=2)
    elif s.startswith("# "): doc.add_heading(s[2:], level=1)
    elif s.startswith("- ") or s.startswith("* "): doc.add_paragraph(s[2:], style="List Bullet")
    else: doc.add_paragraph(s)
doc.save("/workspace/output.docx")
print("OK")
```

### html → pdf

```python
from weasyprint import HTML
HTML(filename="/workspace/input.html").write_pdf("/workspace/output.pdf")
print("OK")
```

## 注意事项

- 先确认源文件存在：`sandbox_run("ls -la /workspace/input.docx")` 
- 转换脚本过长的，用 `sandbox_write_file` 写入而非嵌在 `sandbox_run` 里
- 完成后用 `sandbox_export_file` 导出结果给用户
- 如果转换失败，检查依赖是否已安装（`pip list | grep 包名`），按需 `pip install`
- 图片提取使用 `base64` 嵌入 HTML，无需额外文件
