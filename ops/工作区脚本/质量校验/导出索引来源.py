#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 .10 上导出 RAG 索引里引用到的全部文档来源（去重），供本地核对"原文 PDF 是否齐备"。

输出：/tmp/sources.txt，每行一个 source（形如 生态环境标准规范/…/xxx.md）
用法：python 导出索引来源.py [/data/fagui_rag/index/chunks.jsonl] [/tmp/sources.txt]
"""
import json
import sys

src = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index/chunks.jsonl"
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sources.txt"

seen: set[str] = set()
n = 0
with open(src, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            seen.add(json.loads(line)["source"])
        except Exception:
            pass

with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(sorted(seen)))

print(f"chunk 总数 {n}，去重后文档 {len(seen)} 个 -> {out}")
print("前缀分布：")
from collections import Counter
for k, v in Counter(s.split("/")[0] for s in seen).most_common():
    print(f"    {k}: {v}")
