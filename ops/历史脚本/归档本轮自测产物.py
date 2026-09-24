#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**本次会话**（2026-09-18 08:1x）自测产生的草稿移入归档子目录。

只动本次会话产生的文件，不碰项目历史产物。移动，不删除。
"""
from __future__ import annotations

import os
import shutil

OUT = "/data/eia_report_gen/_生成结果"
DEST = os.path.join(OUT, "_站点测试产物")
# 本次会话自测产生的文件名特征（时间戳 20260918-0811）
MARKERS = ("20260918-0811",)

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
    print("  %-78s %d 字节" % (n[:78], s))
print("共 %d 个" % len(moved))

left = [n for n in os.listdir(OUT) if n.endswith(".docx") and os.path.isfile(os.path.join(OUT, n))]
print("\n_生成结果 顶层剩余 .docx：%d 个（本轮测试前为 46）" % len(left))
print("归档目录内容：%d 个" % len(os.listdir(DEST)))
