#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看某一轮探针里指定题目的完整答案。用法：python 看探针答案.py 清理编者按后 18484-限值"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WS = Path(__file__).resolve().parents[2]
label = sys.argv[1]
tag = sys.argv[2] if len(sys.argv) > 2 else None
rows = json.loads((WS / "_工作记录" / f"探标准_{label}.json").read_text(encoding="utf-8"))
for r in rows:
    if tag and r["标签"] != tag:
        continue
    print(f"\n{'=' * 90}\n【{r['标签']}】{r['答案字数']} 字\n")
    print(r["答案"])
