#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：生成稿里"直排"出现在哪 —— 用来定位自审假结论的来源。

用法：/home/test/fagui_serve/.venv/bin/python 查直排来源.py [docx路径]
"""
from __future__ import annotations

import glob
import os
import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

path = sys.argv[1] if len(sys.argv) > 1 else max(
    glob.glob("/data/eia_report_gen/_生成结果/*.docx"), key=os.path.getmtime)
print("文件:", os.path.basename(path))
doc = Document(path)
in_meta, n = False, 0
for ch in doc.element.body.iterchildren():
    tag = ch.tag.split("}")[-1]
    if tag == "p":
        p = Paragraph(ch, doc)
        s = p.text.strip()
        if s.startswith("生成说明（") or s.startswith("附："):
            in_meta = True
        brk = 'w:type="page"' in p._p.xml
        if in_meta:
            if "直排" in s:
                n += 1
                print("  [说明页] %s" % s[:130])
            if brk:
                in_meta = False
            continue
        if "直排" in s:
            n += 1
            print("  [正文段落] %s" % s[:130])
    elif tag == "tbl":
        tb = Table(ch, doc)
        for r in tb.rows:
            cs = [c.text.strip() for c in r.cells]
            if any("直排" in c for c in cs):
                n += 1
                print("  [%s表格行] %s" % ("说明页" if in_meta else "正文", " | ".join(cs)[:130]))
print("共 %d 处" % n)
