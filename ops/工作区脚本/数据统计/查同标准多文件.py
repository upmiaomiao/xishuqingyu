#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出"同一个标准号对应多个文件"的情况：判断它们是同一份内容的不同副本，还是互补的不同章节。

用法：python 查同标准多文件.py [标准号 ...]     默认看 GB 4915-2013 / GB 18599-2020
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

SRC = "/data/fagui_rag/index/chunks.jsonl"
WANT = sys.argv[1:] or ["GB 4915-2013", "GB 18599-2020"]


def norm(s: str) -> str:
    """标准号归一化：统一长破折号/全角减号，去掉多余空格。"""
    for ch in ("—", "－", "–", "~"):
        s = s.replace(ch, "-")
    return " ".join(s.split()).upper()


per_sid: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "ch": 0, "head": ""}))
n_sid: dict[str, set] = defaultdict(set)
for line in open(SRC, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    c = json.loads(line)
    raw = c.get("standard_id") or ""
    if not raw:
        continue
    sid = norm(raw)
    n_sid[sid].add(raw)          # 同一标准号有多少种写法
    e = per_sid[sid][c["source"]]
    e["n"] += 1
    e["ch"] += len(c["text"] or "")
    if not e["head"] and c.get("chunk_index") == 0:
        e["head"] = (c["text"] or "")[:90].replace("\n", " ")
    if not e["head"]:
        e["head"] = (c["text"] or "")[:90].replace("\n", " ")

print(f"索引里 standard_id 归一化后共 {len(per_sid)} 个标准")
multi = {k: v for k, v in per_sid.items() if len(v) > 1}
print(f"其中「一个标准号对应多个文件」的：{len(multi)} 个")
print(f"这些多出来的文件共 {sum(len(v) - 1 for v in multi.values())} 份")
print()

for sid in WANT:
    k = norm(sid)
    files = per_sid.get(k)
    print(f"=== {sid}（写法变体：{sorted(n_sid.get(k, []))}）→ {len(files) if files else 0} 个文件 ===")
    if not files:
        continue
    for s, e in sorted(files.items(), key=lambda x: -x[1]["ch"]):
        print(f"   {e['ch']:6d}字 {e['n']:3d}块  {s[:100]}")
        print(f"        开头：{e['head'][:80]}")
    print()
