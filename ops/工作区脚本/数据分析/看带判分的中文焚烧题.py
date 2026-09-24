#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出带**直接判分**的中文垃圾焚烧题（专业案例 / 黄金样本），作为 20 条的硬证据来源。"""
from __future__ import annotations

import json
from pathlib import Path

WS = Path(__file__).resolve().parents[2]


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def dims(j: dict) -> dict:
    return {k: v for k, v in (j or {}).items() if k != "brief"}


print("=" * 100)
print("■ 专业案例/专业难题展示案例.jsonl")
rows = list(load(WS / "专业案例" / "专业难题展示案例.jsonl"))
print(f"  条数 {len(rows)}")
for r in sorted(rows, key=lambda x: -(x.get("score") or 0)):
    q = " ".join(r["question"].split())
    print(f"  score={r.get('score')} diff={r.get('diff')} route={r.get('route')} "
          f"cites={r.get('sources')} judge={dims(r.get('judge'))}")
    print(f"     {q[:180]}")

print()
print("=" * 100)
print("■ 黄金样本/golden_judged.jsonl：type ∈ {wte_zh, identity, wte_en/field}")
for r in load(WS / "黄金样本" / "golden_judged.jsonl"):
    if r.get("type") in ("wte_zh", "identity", "wte_en/field"):
        q = " ".join(r["question"].split())
        print(f"  [{r.get('type')}] total={r.get('total')} jscore={r.get('jscore')} "
              f"五维={dims(r.get('judge'))}")
        print(f"     {q[:175]}")

print()
print("=" * 100)
print("■ 日常案例 里带判分的（demo_judged / judged）")
for name in ("日常案例/demo_judged.jsonl", "日常案例/judged.jsonl"):
    p = WS / name
    if not p.is_file():
        continue
    rows = list(load(p))
    print(f"  {name}：{len(rows)} 条，字段 {list(rows[0].keys()) if rows else '—'}")
    for r in rows[:4]:
        q = " ".join(str(r.get("question", "")).split())
        print(f"     score={r.get('score')} judge={dims(r.get('judge'))}  {q[:130]}")
