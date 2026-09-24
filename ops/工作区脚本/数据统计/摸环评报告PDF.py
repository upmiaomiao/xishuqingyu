#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摸清环评报告 PDF 的可解析程度：文本层、页数、目录、关键章节与页码定位。

审核智能体要输出"环评文件 + 页码"（截图里是 -P19），所以必须先确认：
PDF 有没有文本层、页号能不能对上、表格是不是图、关键章节能否自动定位。
"""
import os
import re

import fitz

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"

# 审核项关心的关键锚点（对应截图中各类审核意见）
ANCHORS = {
    "专项评价设置": r"专项评价",
    "评价等级": r"评价等级",
    "环境敏感目标": r"环境保护目标|敏感目标",
    "原辅材料": r"原辅材料|主要原辅料",
    "分类管理名录": r"分类管理名录",
    "编制依据": r"编制依据",
    "地下水": r"地下水",
    "大气": r"大气环境",
    "二噁英": r"二噁英",
    "排污许可": r"排污许可",
}

for name in sorted(os.listdir(ROOT)):
    if not name.lower().endswith(".pdf"):
        continue
    p = os.path.join(ROOT, name)
    try:
        d = fitz.open(p)
    except Exception as e:
        print(f"--- {name}: 打开失败 {e}")
        continue
    pages = d.page_count
    chars = sum(len(d[i].get_text()) for i in range(pages))
    toc = d.get_toc()
    # 图片数（判断是否扫描件）
    imgs = sum(len(d[i].get_images(full=True)) for i in range(min(pages, 40)))
    scan_like = chars / max(pages, 1) < 120
    print(f"\n=== {name[:60]}")
    print(f"    {pages} 页  {chars:,} 字  {chars/max(pages,1):.0f} 字/页  "
          f"前40页内嵌图 {imgs} 张  目录条目 {len(toc)}  "
          f"{'⚠疑似扫描件' if scan_like else ''}")
    if toc:
        print("    目录前 6 条:")
        for lvl, title, pg in toc[:6]:
            print(f"      {'  '*(lvl-1)}{title[:44]}  → p{pg}")
    # 关键锚点定位（前 5 个命中页）
    hits = {}
    for i in range(pages):
        t = d[i].get_text()
        for k, rx in ANCHORS.items():
            if k in hits:
                continue
            if re.search(rx, t):
                hits[k] = i + 1
    print(f"    锚点首现页: {hits}")
    d.close()
