#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读盘点线上检索索引：语料构成、字段、副本情况。

在 .10 上跑：/home/test/fagui_serve/.venv/bin/python 查索引构成.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")
print(f"索引文件 {IDX}  {IDX.stat().st_size/1048576:.1f} MB")

types: Counter = Counter()
corpus: Counter = Counter()
stems: Counter = Counter()
total = 0
sample = None
with IDX.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        total += 1
        if sample is None:
            sample = {k: (str(v)[:60]) for k, v in c.items()}
        types[c.get("type") or "(空)"] += 1
        src = c.get("source") or ""
        corpus[src.split("/")[0]] += 1
        stems[src] += 1

print(f"\n总 chunk {total:,}")
print("\n按 type：")
for k, v in types.most_common():
    print(f"   {k:20s} {v:9,d}  {v/total*100:5.1f}%")
print("\n按语料（source 顶层目录）：")
for k, v in corpus.most_common():
    print(f"   {k:24s} {v:9,d}  {v/total*100:5.1f}%")

print(f"\n唯一来源文件 {len(stems)} 份")
# 副本：名字以 copy / (1) / （1） / 副本 结尾的
dup = [s for s in stems if re.search(r"(copy|副本|\(\d+\)|（\d+）|\s-\s*副本)\s*$", s, re.I)]
print(f"名字带 copy/副本/序号 的来源 {len(dup)} 份，占用 chunk {sum(stems[s] for s in dup):,}")
for s in sorted(dup)[:15]:
    print(f"   {stems[s]:6,d}  {s}")

# 更狠的一层：按「去掉 copy 后缀」归一后有重复的
norm: dict[str, list[str]] = {}
for s in stems:
    k = re.sub(r"[\s_-]*(copy|副本)\s*$", "", s, flags=re.I)
    k = re.sub(r"\s*\(\d+\)\s*$", "", k)
    norm.setdefault(k, []).append(s)
multi = {k: v for k, v in norm.items() if len(v) > 1}
print(f"\n归一（去 copy/序号）后仍有 {len(multi)} 组重复，涉及 {sum(len(v) for v in multi.values())} 份文件、"
      f"{sum(stems[s] for v in multi.values() for s in v):,} chunk")
for k, v in sorted(multi.items(), key=lambda x: -sum(stems[s] for s in x[1]))[:10]:
    print(f"   {sum(stems[s] for s in v):6,d} chunk  {len(v)} 份：{k[:70]}")
    for s in v[:3]:
        print(f"            - {stems[s]:6,d}  {s}")

print("\n首条 chunk 的字段：")
for k, v in (sample or {}).items():
    print(f"   {k:16s} = {v}")
