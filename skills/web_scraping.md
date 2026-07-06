# 网页爬取技能

## 适用场景

当用户要求爬取网站内容、提取网页数据、批量抓取页面时，激活此技能。

## 工作流程

1. **确认目标**：用户要爬什么？单页还是多页？要提取什么字段？
2. **单页抓取**：先用 fetch_webpage 工具试一个页面
3. **结构化提取**：如果需要特定字段，在沙盒里用 BeautifulSoup 解析
   ```python
   from bs4 import BeautifulSoup
   import httpx
   resp = httpx.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
   soup = BeautifulSoup(resp.text, 'lxml')
   # 提取标题
   titles = [h2.text.strip() for h2 in soup.find_all('h2')]
   ```
4. **批量抓取**：多页面时加延时（`time.sleep(1)`），避免被 ban
5. **导出结果**：数据存为 CSV/JSON，用 sandbox_export_file 导出

## 注意事项

- 遵守 robots.txt，不爬禁止抓取的页面
- 设置合理的 User-Agent
- 单次抓取不超过 20 个页面
- 遇到反爬（403/429）时停止并告知用户
- 结构化数据优先用 CSV 导出
