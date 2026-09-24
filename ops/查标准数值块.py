#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查 GB 18599-2020 里"含数值的块"是否在索引中，以及它排在第几块。

用途：I 类场防渗那个问题之所以答不出，要分清是"库里没有数值"还是"召回到了没数值的块"。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")
NEEDLE = "GB 18599"
PAT = re.compile(r"渗透系数|1\.0\s*[×x]\s*10|10\s*[-−–－]\s*5|cm/s")

hits = []
with IDX.open(encoding="utf-8") as fh:
    for line in fh:
        c = json.loads(line)
        src = c.get("source") or ""
        if NEEDLE in src:
            hits.append(c)

print(f"含「{NEEDLE}」的来源文件 {len({c['source'] for c in hits})} 份，共 {len(hits)} 块")
for src in sorted({c["source"] for c in hits}):
    n = sum(1 for c in hits if c["source"] == src)
    print(f"   {n:4d} 块  {src}")

for src in sorted({c["source"] for c in hits}):
    sub = [c for c in hits if c["source"] == src]
    withnum = [c for c in sub if PAT.search(c.get("text") or "")]
    print(f"\n=== {src}")
    print(f"    总块 {len(sub)}，含'渗透系数/1.0×10/10-5/cm/s'的块 {len(withnum)}")
    for c in withnum[:6]:
        t = re.sub(r"\s+", " ", c.get("text") or "")
        print(f"    chunk#{c.get('chunk_index')}: …{t[:300]}…")
