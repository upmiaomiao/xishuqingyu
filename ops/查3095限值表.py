#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：把 GB 3095—2026 的浓度限值表原文抠出来，确认"过渡阶段"与"第二阶段"各是多少。

为什么要抠：问答里那条错例是"PM10 年均二级答 50"，而 2026 版是**分两阶段**实施的，
2026-03-01～2030-12-31 执行过渡阶段限值 —— 想写一句准确的导读，数值必须有出处。
"""
from __future__ import annotations

import io
import json
import re

IDX = "/data/fagui_rag/index/chunks.jsonl"
WANT = "环境空气质量标准（GB 3095—2026）"
hits = []
with io.open(IDX, encoding="utf-8", errors="replace") as f:
    for line in f:
        if WANT not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if WANT in (o.get("source") or ""):
            hits.append(o)

print(f"该文档在索引里 {len(hits)} 块")
for o in hits:
    t = (o.get("text") or "").replace("\n", " ")
    if not re.search(r"限值|浓度|阶段|年平均|日均", t):
        continue
    print("\n" + "-" * 96)
    print(f"[块 {o.get('chunk_index')}] status={o.get('status')}")
    print(t[:1400])
