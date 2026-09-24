#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按**时间戳**归档剩余探针产物，并顺便用码点核对文件名（避免终端编码干扰判断）。"""
import os
import shutil

OUT = "/data/eia_report_gen/_生成结果"
DEST = os.path.join(OUT, "_站点测试产物")
os.makedirs(DEST, exist_ok=True)

for n in sorted(os.listdir(OUT)):
    if "3000" in n:
        print("码点:", " ".join("%04x" % ord(c) for c in n[:14]))
        print("字符:", " ".join(c for c in n[:14]))

# 我这次对话式测试产物的时间戳（前面三个已按名字归档）
for n in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, n)
    if os.path.isfile(p) and n.endswith(".docx") and "131956" in n:
        shutil.move(p, os.path.join(DEST, n))
        print("\n已归档:", n)

left = [n for n in os.listdir(OUT) if n.endswith(".docx") and os.path.isfile(os.path.join(OUT, n))]
print("\n顶层剩余 .docx：%d 个；归档目录：%d 个" % (len(left), len(os.listdir(DEST))))
