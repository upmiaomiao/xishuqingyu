#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化「查看原文 PDF」这个用户可见功能的真实命中率。

引用卡片上的「📄 查看原文 PDF」走 /doc?source=<索引里的 .md 路径>，
而 /doc 只回 PDF_ROOT 下真实存在的同名 .pdf。索引里有 265k chunks、4052 个文件，
到底多少个能点开，得实测，不能靠感觉。
"""
from __future__ import annotations

import json
import os
import random

INDEX = "/data/fagui_rag/index/chunks.jsonl"
PDF_ROOT = "/data/fagui_pdf"

sources = set()
with open(INDEX, encoding="utf-8") as f:
    for line in f:
        try:
            o = json.loads(line)
        except Exception:                                      # noqa: BLE001
            continue
        s = o.get("source")
        if s:
            sources.add(s)

print("索引里不同的 source 数：%d" % len(sources))
print("PDF_ROOT：%s（存在=%s）" % (PDF_ROOT, os.path.isdir(PDF_ROOT)))

hit = miss = 0
miss_sample = []
for s in sources:
    stem = s[:-3] if s.lower().endswith(".md") else s
    p = os.path.join(PDF_ROOT, stem + ".pdf")
    if os.path.isfile(p):
        hit += 1
    else:
        miss += 1
        if len(miss_sample) < 12:
            miss_sample.append(s)

tot = hit + miss
print("\n★ 能点开的（同名 .pdf 存在）：%d / %d = %.1f%%" % (hit, tot, 100.0 * hit / max(tot, 1)))
print("★ 点开会 404 的        ：%d / %d = %.1f%%" % (miss, tot, 100.0 * miss / max(tot, 1)))
print("\n缺 PDF 的样例：")
for s in miss_sample:
    print("  %s" % s[:110])

# 反向：PDF_ROOT 里有 PDF、但索引里没有任何 chunk 指向它（点了也到不了）
if os.path.isdir(PDF_ROOT):
    pdfs = set()
    for root, _dirs, files in os.walk(PDF_ROOT):
        for n in files:
            if n.lower().endswith(".pdf"):
                pdfs.add(os.path.relpath(os.path.join(root, n), PDF_ROOT)[:-4].replace("\\", "/"))
    print("\nPDF_ROOT 下 PDF 总数：%d" % len(pdfs))
    stems = {s[:-3] if s.lower().endswith(".md") else s for s in sources}
    orphan = pdfs - stems
    print("其中索引里没有任何引用指向的（用户永远点不到）：%d" % len(orphan))
    for s in sorted(orphan)[:8]:
        print("  %s" % s[:110])
