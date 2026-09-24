#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：GB 3095—2026 在索引里的 11 块到底装了什么 —— 特别是"表1 浓度限值"进没进索引。

背景：问答错例是"PM10 年均二级答 50"。如果表1 的数字压根没进索引，
那这条就不是状态标记问题，而是**切块把表格丢了**（与 [016] 同一类）。
"""
from __future__ import annotations

import io
import json
import re

IDX = "/data/fagui_rag/index/chunks.jsonl"
KEYS = ["环境空气质量标准（GB 3095—2026）", "环境空气质量标准 GB 3095—2026代替"]
docs = {}
with io.open(IDX, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "3095" not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        src = o.get("source") or ""
        if "3095" not in src:
            continue
        docs.setdefault(src, []).append(o)

for src, rows in docs.items():
    rows.sort(key=lambda x: x.get("chunk_index") or 0)
    has_num = sum(1 for r in rows if re.search(r"\b(15|25|30|35|40|50|60|70|80|150|160)\b",
                                               r.get("text") or ""))
    print("=" * 100)
    print(f"{src}")
    print(f"  块数 {len(rows)}　含两位数限值数字的块 {has_num}")
    for r in rows:
        t = (r.get("text") or "").replace("\n", " ")
        print(f"  --- [{r.get('chunk_index')}] status={r.get('status')} 长度 {len(t)}")
        print("      " + t[:260])
