#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本次站点测试产生的**探针产物**移进子目录归档（移动，不删除）。

纪律：归档不删除。所以只 shutil.move，不做 unlink。
移走的动机：这些文件名里带 HTML 探针串 / 穿越串，会出现在用户「历史报告」列表里，
属于测试污染，不该留在用户可见的清单中。
"""
from __future__ import annotations

import os
import shutil

OUT = "/data/eia_report_gen/_生成结果"
DEST = os.path.join(OUT, "_站点测试产物")

# 只认这几个特征，避免误伤项目自己的 e2e 产物。
# 「塑料制品」是本套件对话式用例的项目描述特征（模型会把【站点测试】前缀吃掉，
# 所以不能只靠前缀匹配 —— 实测踩到过，第一次漏了一个文件）。
MARKERS = ("onerror=alert", "tmp_evil_probe", "塑料制品")

os.makedirs(DEST, exist_ok=True)
moved = []
for n in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, n)
    if not os.path.isfile(p) or not n.endswith(".docx"):
        continue
    if any(m in n for m in MARKERS):
        shutil.move(p, os.path.join(DEST, n))
        moved.append((n, os.path.getsize(os.path.join(DEST, n))))

print("移入 %s：" % DEST)
for n, s in moved:
    print("  %-95s %d 字节" % (n[:95], s))
print("共 %d 个" % len(moved))

left = [n for n in os.listdir(OUT) if n.endswith(".docx") and os.path.isfile(os.path.join(OUT, n))]
print("\n_生成结果 顶层剩余 .docx：%d 个" % len(left))
print("归档目录内容：%d 个" % len(os.listdir(DEST)))
