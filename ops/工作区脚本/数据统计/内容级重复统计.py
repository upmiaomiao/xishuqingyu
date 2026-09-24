#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按**正文内容哈希**统计索引里真正的重复（同一份内容挂了多个 source）。

标题相同但内容不同（不同年份的公告、不同期的通报）**不算重复**。

用法：python 内容级重复统计.py [/data/fagui_rag/index/chunks.jsonl]
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index/chunks.jsonl"

docs: dict[str, list[str]] = defaultdict(list)
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        docs[c.get("source", "")].append(c.get("text") or "")

by_hash: dict[str, list[str]] = defaultdict(list)
sizes: dict[str, int] = {}
for s, texts in docs.items():
    body = "\n".join(texts)
    h = hashlib.sha256(body.encode()).hexdigest()
    by_hash[h].append(s)
    sizes[h] = len(body)

groups = {h: ss for h, ss in by_hash.items() if len(ss) > 1}
extra = sum(len(ss) - 1 for ss in groups.values())
total = len(docs)
dup_chars = sum(sizes[h] * (len(ss) - 1) for h, ss in groups.items())

print(f"索引文档总数：{total}")
print(f"内容完全相同的组：{len(groups)} 组")
print(f"多余副本（真重复）：{extra} 份  （占 {extra/total*100:.1f}%）")
print(f"重复占用的正文体量：约 {dup_chars/10000:.0f} 万字")
print()
print("=== 重复最多的 12 组 ===")
for h, ss in sorted(groups.items(), key=lambda x: -len(x[1]))[:12]:
    print(f"  {len(ss)} 份 × {sizes[h]:6d} 字   {ss[0].split('/')[-1][:52]}")
    for s in ss[1:4]:
        print(f"        副本: {s[:100]}")
    if len(ss) > 4:
        print(f"        …另 {len(ss)-4} 份")
print()
same_title = sum(1 for h, ss in by_hash.items() if len(ss) > 1)
print("=== 对照：标题相同但内容不同的组（**不算重复**）===")
titles: dict[str, set] = defaultdict(set)
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            c = json.loads(line)
            titles[c.get("title") or ""].add(c.get("source", ""))
multi = {t: ss for t, ss in titles.items() if t and len(ss) > 1}
print(f"  同名 {len(multi)} 组，共 {sum(len(v) for v in multi.values())} 个 source")
print(f"  真重复（内容级）的组数：{len(groups)}，多余 {extra} 份")
