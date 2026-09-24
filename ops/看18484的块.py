#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看 GB 18484 的块：表 3 是怎么被切开的（后半段还有没有表头/表号）。"""
import json

SRC = "生态环境标准规范/国家排放标准/危险废物焚烧污染控制标准 GB 18484-2020/"
rows = []
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        if (o.get("source") or "").startswith(SRC.rstrip("/")):
            rows.append(o)
print(f"GB 18484 共 {len(rows)} 块")
for o in rows:
    t = o["text"]
    if any(k in t for k in ("表 3", "汞及其化合物", "二噁英类", "颗粒物")):
        head = t[:110].replace("\n", " ⏎ ")
        tail = t[-90:].replace("\n", " ⏎ ")
        print(f"\n--- #{o['chunk_index']}  {len(t)} 字 ---")
        print(f"  头：{head}")
        print(f"  尾：{tail}")
