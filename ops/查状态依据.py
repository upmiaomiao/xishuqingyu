#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读探针：新索引里 status_note 到底写了什么依据（按来源归并，看有没有"只说自己"的空话）。

用法：python 查状态依据.py /data/fagui_rag/index_v5_note
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict

d = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index_v5_note"
notes = defaultdict(Counter)
status = defaultdict(Counter)
KEY = ("环评法", "固废法", "固体废物污染环境防治法", "环境影响评价法", "3095", "法典")

with io.open(d + "/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        try:
            o = json.loads(line)
        except Exception:
            continue
        n = (o.get("status_note") or "").strip()
        s = (o.get("status") or "").strip()
        src = (o.get("source") or "")
        if n:
            notes[src][n] += 1
        if "已废止" in s or "废止" in s:
            status[src][s] += 1

print("===== 1) 有 status_note 的来源数：%d =====" % len(notes))
allnotes = Counter()
for src, c in notes.items():
    for n, k in c.items():
        allnotes[n] += k
print("===== 2) 依据全文去重（出现次数）=====")
for n, k in allnotes.most_common():
    print(f"  ×{k:<4} {n}")

print("\n===== 3) 用户错例点名的 3 份材料，依据是什么 =====")
for src, c in notes.items():
    if any(k in src for k in KEY):
        for n, k in c.items():
            print(f"  [{k:>3} 块] status={list(status[src].keys())}")
            print(f"     来源：{src[:110]}")
            print(f"     依据：{n}")
