#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建结果只差末尾换行，试几种结尾找出与原版逐字节一致的那一种。"""
from __future__ import annotations

import hashlib
import io

WANT = "c7f10340fd47f4472493a184303af23c"
P = r"_中间产物/线上源码/gen_routes.py"

src = io.open(P, encoding="utf-8").read()
src = src.replace("import os\nimport shutil\nimport sys\n", "import os\nimport sys\n", 1)
src = src.replace(
    'OUT_DIR = os.path.join(GEN_HOME, "_生成结果")\n'
    'ARCHIVE_DIR = os.path.join(OUT_DIR, "_已归档")     # 归档目录：放在 OUT_DIR 下，列表只扫 *.docx 所以不会显示出来\n',
    'OUT_DIR = os.path.join(GEN_HOME, "_生成结果")\n', 1)
cut = src.find("\n\ndef _resolve_output(")
if cut > 0:
    src = src[:cut] + "\n"

base = src.rstrip("\n")
print("去掉尾部换行后行数：%d" % (base.count("\n") + 1))
print()

variants = {
    "无末尾换行": base,
    "一个换行": base + "\n",
    "两个换行": base + "\n\n",
    "三个换行": base + "\n\n\n",
}
hit = None
for label, text in variants.items():
    got = hashlib.md5(text.encode("utf-8")).hexdigest()
    mark = "★ 命中" if got == WANT else ""
    print("  %-10s %s  %s" % (label, got, mark))
    if got == WANT:
        hit = text

if hit is None:
    print("\n仍不匹配 —— 说明差异不止末尾换行，不能当备份用。")
    raise SystemExit(1)

io.open(r"_中间产物/线上源码/gen_routes.py.原版", "w", encoding="utf-8", newline="").write(hit)
print("\n已写为 _中间产物/线上源码/gen_routes.py.原版")
