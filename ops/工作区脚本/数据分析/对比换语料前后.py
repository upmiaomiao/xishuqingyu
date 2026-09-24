#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比换语料前后的答案：关键数字/标准号在不在，字数变化。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WS = Path(__file__).resolve().parents[2]

before = {r["标签"]: r for r in json.loads(
    (WS / "_工作记录" / "探标准_换语料前.json").read_text(encoding="utf-8"))}
after = {r["标签"]: r for r in json.loads(
    (WS / "_工作记录" / "探标准_换语料后.json").read_text(encoding="utf-8"))}

KEYS = {
    "18485-限值": ["30", "20", "300", "250", "100", "80", "50", "60", "0.05", "0.1", "1.0"],
    "18485-技术性能": ["850", "2 秒", "2秒", "5%", "5 %", "热灼减率"],
    "18484-限值": ["30", "20", "300", "250", "0.5", "0.05", "2.0", "二噁英"],
    "飞灰处置": ["HJ 1134", "1134", "螯合", "填埋", "GB 16889", "危险废物", "水泥窑"],
}

for tag in before:
    b, a = before[tag], after.get(tag, {})
    ba, aa = b.get("答案") or "", a.get("答案") or ""
    print(f"\n{'='*90}\n【{tag}】答案 {len(ba)} 字 → {len(aa)} 字；"
          f"引用 {len(b.get('引用') or [])} → {len(a.get('引用') or [])}；"
          f"本体命中 {b.get('本体命中')} → {a.get('本体命中')}")
    print("  关键词：")
    for k in KEYS.get(tag, []):
        mark = ("✅" if k in ba else "❌") + "→" + ("✅" if k in aa else "❌")
        if k in ba or k in aa:
            print(f"    {mark}  {k}")
    print(f"  ── 换语料后答案开头 420 字 ──\n{aa[:420]}")
