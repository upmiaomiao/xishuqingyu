#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核实"同名重复"里有多少是**真重复**（内容一致）而非"标题相同但内容不同"。

用法：python 核实重复文档.py [标题关键词 ...]
默认核查几个高频标题。
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict

SRC = "/data/fagui_rag/index/chunks.jsonl"
TITLES = sys.argv[1:] or ["水泥工业大气污染物排放标准", "中央生态环境保护督察集中通报典型案例",
                          "环境影响评价技术导则 声环境"]

by_title: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        t = c.get("title") or ""
        if t in TITLES:
            by_title[t][c.get("source", "")].append(c.get("text") or "")

for t in TITLES:
    docs = by_title.get(t)
    if not docs:
        print(f"「{t}」：索引里没有\n")
        continue
    print(f"=== 「{t}」 共 {len(docs)} 个 source ===")
    sigs = {}
    for s, texts in sorted(docs.items(), key=lambda x: -sum(len(v) for v in x[1])):
        body = "\n".join(texts)
        h = hashlib.sha256(body.encode()).hexdigest()[:8]
        sigs.setdefault(h, []).append(s)
        print(f"    {len(body):7d} 字  哈希{h}  {s[:96]}")
    uniq = len(sigs)
    print(f"    → 不同内容 {uniq} 种；"
          f"{'✅ 全部互不相同' if uniq == len(docs) else '⚠️ 有真重复'}")
    for h, ss in sigs.items():
        if len(ss) > 1:
            print(f"      真重复({len(ss)} 份, 哈希{h}): {[x.split('/')[-1][:40] for x in ss]}")
    print()
