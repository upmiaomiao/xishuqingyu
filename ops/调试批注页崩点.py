# -*- coding: utf-8 -*-
"""定位崩溃点：逐页取批注、逐条读 title/rect，每步都先打印。"""
import os
import sys

import pymupdf

OUT = "/data/eia_audit/_审核结果/导出"
path = None
for f in sorted(os.listdir(OUT)):
    if f.endswith(".批注版.pdf") and "临沂" in f:
        path = os.path.join(OUT, f)
        break
print("打开", os.path.basename(path), flush=True)
doc = pymupdf.open(path)
print("页数", doc.page_count, flush=True)
for i in range(doc.page_count):
    print("  页 P%d ..." % (i + 1), end="", flush=True)
    anns = list(doc[i].annots() or [])
    print(" 批注 %d" % len(anns), end="", flush=True)
    for an in anns:
        t = (an.info or {}).get("title") or ""
        r = an.rect
        print(" [%s %s]" % (t[:18], tuple(round(v) for v in r)), end="", flush=True)
    print("", flush=True)
    if len(anns):
        print("     ↑ 这一页要渲图 ...", end="", flush=True)
        pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0))
        print(" 渲好 %dx%d" % (pix.width, pix.height), flush=True)
print("全部完成", flush=True)
doc.close()
