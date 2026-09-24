#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看实跑结果：引用来源构成 + 答案节选（挑几条关键的）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
IN = WS / "_工作记录" / "实跑20条_输出.jsonl"

rows = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]
want = {int(x) for x in sys.argv[1].split(",")} if len(sys.argv) > 1 else {16, 17, 18, 19, 20}

for r in rows:
    if r["序号"] not in want:
        continue
    print("=" * 104)
    print(f"【{r['序号']}】{r['题型']}　{ r['耗时s']}s　答案 {r['答案字数']} 字　引用 {r['引用条数']} 条")
    print(f"题目：{' '.join(r['题目'].split())[:200]}")
    print("引用来源：")
    for i, s in enumerate(r.get("引用来源") or [], 1):
        print(f"   {i:>2}. {s}")
    ans = " ".join((r.get("答案") or "").split())
    print(f"答案节选：{ans[:900]}")
    print()
