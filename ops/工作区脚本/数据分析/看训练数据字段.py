#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼几个训练数据的字段结构（只看前几条，不整文件读进内存）。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]

FILES = [
    "焚烧测试/wte_test_questions.jsonl",
    "焚烧测试/wte_v5_judged.jsonl",
    "焚烧测试/wte_v5c_judged.jsonl",
    "黄金样本/golden_20.jsonl",
    "黄金样本/golden_judged.jsonl",
    "专业案例/专业难题展示案例.jsonl",
    "原始训练数据/sft3_accepted_strict_merged.jsonl",
    "合并训练数据/sft_merged_train.jsonl",
    "原始训练数据/wte_sft_english_20k_v2.jsonl",
]


def head(p: Path, n=2):
    out = []
    with p.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def brief(v, width=110):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s[:width] + ("…" if len(s) > width else "")


for rel in FILES:
    p = WS / rel
    if not p.is_file():
        print(f"❓ 缺 {rel}")
        continue
    print("=" * 100)
    print(f"■ {rel}   {p.stat().st_size/1024/1024:.1f} MB")
    rows = head(p, 2)
    if not rows:
        print("  （空）")
        continue
    print(f"  字段：{list(rows[0].keys())}")
    for r in rows:
        for k, v in r.items():
            print(f"    {k:<16}{brief(v)}")
        print("    " + "-" * 90)

    # 统计 messages 式数据的角色构成（sft 常见格式）
    if "messages" in rows[0]:
        c = Counter()
        with p.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 200:
                    break
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                c[tuple(m.get("role") for m in r.get("messages", []))] += 1
        print(f"  前 200 条的 messages 角色构成：{dict(c)}")
