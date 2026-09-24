#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对某份文档在索引里的实际内容与切片情况（默认查 HJ 2.1 总纲）。

用法：python 查文档内容.py <标题关键词>
"""
from __future__ import annotations

import json
import sys
from collections import Counter

SRC = "/data/fagui_rag/index/chunks.jsonl"
KW = sys.argv[1] if len(sys.argv) > 1 else "环境影响评价技术导则 总纲"

found: dict[str, list[dict]] = {}
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        if KW in (c.get("title") or ""):
            found.setdefault(c.get("source", ""), []).append(c)

print(f"匹配「{KW}」的文档：{len(found)} 份")
for src, chunks in found.items():
    chunks.sort(key=lambda c: c.get("chunk_index", 0))
    total = sum(len(c.get("text") or "") for c in chunks)
    print(f"\n=== {chunks[0].get('title')}  [{chunks[0].get('standard_id')}] ===")
    print(f"    source : {src}")
    print(f"    分块数 : {len(chunks)}   正文合计 {total} 字")
    for c in chunks[:3]:
        t = (c.get("text") or "").replace("\n", " ")
        print(f"      #{c.get('chunk_index')} ({len(c.get('text') or '')}字): {t[:220]}")
    if len(chunks) > 3:
        t = (chunks[-1].get("text") or "").replace("\n", " ")
        print(f"      …最后一块 #{chunks[-1].get('chunk_index')}: {t[:160]}")
