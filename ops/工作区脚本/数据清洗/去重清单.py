#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成索引去重清单（**不删除任何文件**），并顺带体检嵌入服务。

重复判定：**正文内容哈希完全相同**（标题相同但内容不同的不算）。
保留策略：候选路径按 (是否含 _1, 路径层数, 路径长度) 升序，保留第一个，其余列为待删。

用法：
  python 去重清单.py                 # 只在 /data/fagui_rag 内生成 /tmp/dedup_plan.json
  python 去重清单.py --check-embed   # 额外测一下 BGE-M3 服务
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict

SRC = "/data/fagui_rag/index/chunks.jsonl"
BUNDLE = "/data/fagui_rag/okf_bundles"
OUT = "/tmp/dedup_plan.json"

docs: dict[str, list[str]] = defaultdict(list)
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        docs[c.get("source", "")].append(c.get("text") or "")

by_hash: dict[str, list[str]] = defaultdict(list)
for s, texts in docs.items():
    by_hash[hashlib.sha256("\n".join(texts).encode()).hexdigest()].append(s)

groups = {h: sorted(ss, key=lambda p: ("_1" in p, p.count("/"), len(p)))
          for h, ss in by_hash.items() if len(ss) > 1}

keep, drop = [], []
for h, ss in groups.items():
    keep.append(ss[0])
    for s in ss[1:]:
        drop.append({"source": s, "keep": ss[0], "hash": h[:10]})

chars = sum(len("\n".join(docs[s])) for d in drop)
plan = {"total_docs": len(docs), "dup_groups": len(groups), "drop_count": len(drop),
        "drop_chars": chars, "keep": keep, "drop": drop}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(plan, fh, ensure_ascii=False, indent=1)

print(f"索引文档 {len(docs)}；重复组 {len(groups)}；将删除 {len(drop)} 份（约 {chars/10000:.0f} 万字）")
print(f"保留 {len(keep)} 份")
print(f"清单已写 {OUT}")
print()
print("=== 待删清单（前 20 组，格式：待删 ← 保留）===")
for d in drop[:20]:
    print(f"  删 {d['source'][:96]}")
    print(f"     ← 留 {d['keep'][:96]}")
print()
# 核对：每个待删 source 在 bundles 里是否真存在
import os
miss = [d["source"] for d in drop if not os.path.isfile(os.path.join(BUNDLE, d["source"]))]
print(f"待删文件在 okf_bundles 里缺失的：{len(miss)}（应为 0）")
if miss[:3]:
    for m in miss[:3]:
        print("   ", m)

if "--check-embed" in sys.argv:
    import requests
    for port in (33004, 34004):
        try:
            r = requests.post(f"http://127.0.0.1:{port}/v1/embeddings",
                              json={"model": "BGE-M3", "input": ["测试"]}, timeout=15)
            n = len(r.json()["data"][0]["embedding"]) if r.status_code == 200 else "-"
            print(f"嵌入服务 :{port} → HTTP {r.status_code} 维度={n}")
        except Exception as e:
            print(f"嵌入服务 :{port} → {type(e).__name__}: {str(e)[:70]}")
