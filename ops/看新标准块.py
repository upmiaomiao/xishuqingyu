#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看新入库两份标准的块：表1/限值表是否自成一块、块内有没有关键数字。"""
import json

SRC = "生态环境标准规范/国家排放标准/生活垃圾焚烧污染控制标准 GB 18485-2014/"
rows = []
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        if (o.get("source") or "").startswith(SRC.rstrip("/")):
            rows.append(o)

print(f"GB 18485 共 {len(rows)} 块：")
for o in rows:
    t = o["text"]
    has = [k for k in ("850", "表 1", "表 4", "0.1 ng", "热灼减率", "2 秒") if k in t]
    if has or o["chunk_index"] < 4:
        print(f"\n--- #{o['chunk_index']}  命中{has}  {len(t)} 字 ---")
        print(t[:300].replace("\n", " ⏎ "))
