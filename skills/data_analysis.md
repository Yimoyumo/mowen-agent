---
name: data_analysis
description: 数据分析、统计计算、生成图表、处理 CSV/JSON/Excel 文件
keywords: [分析, 图表, 统计, CSV, JSON, Excel, pandas, matplotlib, 数据]
---

# 数据分析技能

## 适用场景

当用户要求分析数据、生成图表、统计计算时，激活此技能。

## 工作流程

1. **确认数据来源**：用户上传了什么文件？（CSV/JSON/Excel）
2. **加载数据**：用 pandas 读取文件
   ```python
   import pandas as pd
   df = pd.read_csv('/workspace/data.csv')
   print(df.info())
   print(df.head())
   ```
3. **数据探索**：先看基本信息（行数、列、类型、缺失值）
4. **分析处理**：按用户需求做统计/聚合/筛选
5. **可视化**：用 matplotlib 生成图表，保存为 .png
   ```python
   import matplotlib
   matplotlib.use('Agg')  # 无头模式
   import matplotlib.pyplot as plt
   plt.rcParams['font.sans-serif'] = ['SimHei']  # 中文支持
   ```
6. **导出结果**：用 sandbox_export_file 导出图表/数据文件

## 注意事项

- 图表必须有标题和坐标轴标签
- 数值结果保留合理小数位
- 数据量大时先采样预览再全量处理
- 中文乱码时用 `plt.rcParams['font.sans-serif'] = ['DejaVu Sans']`
