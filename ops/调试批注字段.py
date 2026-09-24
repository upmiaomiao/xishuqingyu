# -*- coding: utf-8 -*-
"""逐项试：P1 那个批注到底是什么，读哪个字段会崩。"""
import os

import pymupdf

OUT = "/data/eia_audit/_审核结果/导出"
path = None
for f in sorted(os.listdir(OUT)):
    if f.endswith(".批注版.pdf") and "临沂" in f:
        path = os.path.join(OUT, f)
        break
doc = pymupdf.open(path)
anns = list(doc[0].annots() or [])
print("P1 批注数", len(anns), flush=True)
an = anns[0]
print("1) 对象拿到:", repr(an)[:80], flush=True)
try:
    print("2) an.type =", an.type, flush=True)
except Exception as e:
    print("2) type 失败", e, flush=True)
try:
    print("3) an.info =", an.info, flush=True)
except Exception as e:
    print("3) info 失败", e, flush=True)
try:
    print("4) an.parent 页号 =", an.parent.number + 1, flush=True)
except Exception as e:
    print("4) parent 失败", e, flush=True)
try:
    print("5) an.rect =", an.rect, flush=True)
except Exception as e:
    print("5) rect 失败", e, flush=True)
print("6) 单独取 rect 再试一次", flush=True)
r = an.rect
print("   rect =", r, flush=True)
print("7) 全部通过", flush=True)
doc.close()
