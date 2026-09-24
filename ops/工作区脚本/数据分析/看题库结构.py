#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看三个题库的字段结构，便于后面按工艺域/题型挑补题。"""
import io
import json
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
FILES = ["原始训练数据/sft3_accepted_strict_merged.jsonl",
         "黄金样本/golden_judged.jsonl",
         "专业案例/专业难题展示案例.jsonl"]

for f in FILES:
    p = WS / f
    n = 0
    first = None
    with io.open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            if first is None:
                first = json.loads(line)
    print(f"\n{'=' * 90}\n{f}　共 {n:,} 条")
    for k, v in first.items():
        s = json.dumps(v, ensure_ascii=False)
        print(f"  {k:<22} {type(v).__name__:<8} {s[:150]}")
