# -*- coding: utf-8 -*-
"""把批注版 PDF 的关键页渲成 PNG，供肉眼核对框得对不对。

为什么要渲图：所有自动检查都只能证明"批注对象存在、坐标非空"，
**证明不了框在正确的字上**。位置错了的检查全绿，正是最该避免的那种"通过"。

踩过的坑（务必留住 page 引用）：
    for an in list(doc[i].annots()): ...   # ← doc[i] 是临时页对象，用完即回收
    之后读 an.rect / an.type 会抛 "annotation not bound to any page"，
    运气不好直接段错误。自检里只读 an.info（不依赖页绑定）所以一直没暴露。
    正确写法：page = doc[i]；再用 page.annots()。
"""
import os
import sys

import pymupdf

OUT = "/data/eia_audit/_审核结果/导出"
PNG = "/tmp/_批注页图"
os.makedirs(PNG, exist_ok=True)

target = sys.argv[1] if len(sys.argv) > 1 else "临沂"
kinds = (sys.argv[2] if len(sys.argv) > 2 else "精确,近似,仅页码").split(",")

path = None
for f in sorted(os.listdir(OUT)):
    if f.endswith(".批注版.pdf") and target in f:
        path = os.path.join(OUT, f)
        break
if not path:
    print("没找到批注版 PDF")
    sys.exit(1)
print("文件：", os.path.basename(path))
doc = pymupdf.open(path)
orig_pages = int(sys.argv[3]) if len(sys.argv) > 3 else doc.page_count - 2

picked = {}
for i in range(orig_pages):
    page = doc[i]                       # ← 必须留住
    for an in page.annots() or []:
        t = (an.info or {}).get("title") or ""
        if not t.startswith("AI审核·"):
            continue
        kind = t.split("·")[1]
        if kind in kinds and kind not in picked:
            # 记下矩形与页高，供本地裁剪用（在页还活着的时候取）
            picked[kind] = (i, tuple(round(v, 1) for v in an.rect),
                            page.rect.width, page.rect.height)
for kind, (i, rect, pw, ph) in picked.items():
    page = doc[i]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0))
    f = os.path.join(PNG, f"{target}_P{i+1}_{kind}.png")
    pix.save(f)
    print("  %-4s → 物理页 P%d  矩形 %s  页面 %.0fx%.0f" % (kind, i + 1, rect, pw, ph))
    print("     %s" % f)

for k, idx in (("汇总1", orig_pages), ("汇总2", orig_pages + 1), ("汇总末", doc.page_count - 1)):
    if 0 <= idx < doc.page_count:
        pix = doc[idx].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6))
        f = os.path.join(PNG, f"{target}_{k}_P{idx+1}.png")
        pix.save(f)
        print("  %s → %s" % (k, f))
doc.close()
