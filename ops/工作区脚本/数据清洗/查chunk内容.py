#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在索引里找关键内容落在哪个 chunk，判断"是没进索引"还是"进了但没被排上来"。

用法：查chunk内容.py <关键词> [索引目录] [最多显示]
"""
import json
import sys

kw = sys.argv[1]
idx = sys.argv[2] if len(sys.argv) > 2 else "/data/fagui_rag/index_stage"
show = int(sys.argv[3]) if len(sys.argv) > 3 else 5

hits = 0
shown = 0
sources = {}
with open(f"{idx}/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        t = o.get("text") or ""
        if kw in t:
            hits += 1
            src = o.get("source", "")
            sources[src] = sources.get(src, 0) + 1
            if shown < show:
                shown += 1
                print(f"--- chunk #{o.get('chunk_index')}  {len(t)} 字  {src[:80]}")
                print(f"    {' '.join(t.split())[:420]}")
print(f"\n含「{kw}」的 chunk 共 {hits} 个，分布在 {len(sources)} 份文档")
for s, n in sorted(sources.items(), key=lambda x: -x[1])[:6]:
    print(f"   {n:4d}  {s[:96]}")
