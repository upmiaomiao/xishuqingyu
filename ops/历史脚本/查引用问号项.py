#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确认引用的 doc_type 缺失项（'?'）是不是知识图谱节点，并统计占比。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in
        (WS / "_工作记录" / "实跑20条_输出v2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

by_type: Counter = Counter()
sq_titles: Counter = Counter()
for r in rows:
    for s in r.get("引用") or []:
        t = s.get("doc_type") or "?"
        by_type[t] += 1
        if t == "?":
            sq_titles[s.get("title") or "（无标题）"] += 1

tot = sum(by_type.values())
print("doc_type 分布：", dict(by_type), f"合计 {tot}")
print(f"\n'?' 共 {by_type['?']} 条，占 {by_type['?']/tot*100:.0f}%；标题样例：")
for t, c in sq_titles.most_common(10):
    print(f"  {c:>3}  {t}")
print(f"\n其中标题以『知识图谱』开头的：{sum(c for t, c in sq_titles.items() if t.startswith('知识图谱'))}")
srcs = Counter()
for r in rows:
    for s in r.get("引用") or []:
        if not s.get("doc_type"):
            srcs[(s.get("source") or "")[:40]] += 1
print("\n'?' 项的 source 前缀：")
for k, v in srcs.most_common(8):
    print(f"  {v:>3}  {k}")
