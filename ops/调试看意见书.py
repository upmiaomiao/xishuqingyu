# -*- coding: utf-8 -*-
"""调试：把生成的意见书正文打出来（看证据行到底写成什么样）。"""
import glob
import os
import sys

from docx import Document

OUT = "/data/eia_audit/_审核结果/导出"
target = sys.argv[1] if len(sys.argv) > 1 else "环评报告"
for p in sorted(glob.glob(os.path.join(OUT, "*.审核意见书.docx"))):
    if target not in os.path.basename(p):
        continue
    print("###", os.path.basename(p))
    d = Document(p)
    body = d.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    n = 0
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            t = Paragraph(child, d).text.strip()
            if t:
                n += 1
                if n <= 200:
                    print("P |", t[:150])
        elif child.tag.endswith("}tbl"):
            tb = Table(child, d)
            for row in tb.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells) and n <= 200:
                    print("T |", " ｜ ".join(c[:60] for c in cells))
    print()
