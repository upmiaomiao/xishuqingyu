#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找出「垃圾焚烧相关 + 判分高」的题型分布（数据源：带 judge 评分的样本）。

判分口径：
  · 黄金样本：judge 五维（correctness/comprehensiveness/structure/actionability/grounding）各 5 分，
    jscore = 五维之和（满分 25）。
  · 焚烧测试：rubric 五维（correctness/coverage/actionability/boundary/overall），
    另有 fabrications（judge 指控的编造处数）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

WS = Path(__file__).resolve().parents[2]

WTE_KW = ("垃圾焚烧", "焚烧", "垃圾发电", "炉排", "渗滤液", "渗沥液", "飞灰", "炉渣", "烟气",
          "二噁英", "GB18485", "GB 18485", "WTE", "wte", "incinerat", "waste-to-energy",
          "MSW", "8#炉", "锅炉", "余热")


def is_wte(rec: dict) -> bool:
    blob = json.dumps(rec, ensure_ascii=False)
    return any(k in blob for k in WTE_KW)


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def score_of(rec: dict) -> float | None:
    j = rec.get("judge")
    if isinstance(j, dict):
        nums = [v for v in j.values() if isinstance(v, (int, float))]
        if nums:
            return float(sum(nums))
    if isinstance(rec.get("jscore"), (int, float)):
        return float(rec["jscore"])
    if isinstance(rec.get("total"), (int, float)):
        return float(rec["total"]) * 100
    return None


print("=" * 100)
print("① 黄金样本：题型 × 判分")
print("=" * 100)
g = WS / "黄金样本" / "golden_judged.jsonl"
by_type = defaultdict(list)
n_wte = 0
for r in load(g):
    t = r.get("type", "?")
    s = score_of(r)
    w = is_wte(r)
    n_wte += w
    if s is not None:
        by_type[(t, w)].append(s)
rows = []
for (t, w), v in by_type.items():
    rows.append((sum(v) / len(v), len(v), t, w))
rows.sort(reverse=True)
print(f"总样本 {sum(len(v) for v in by_type.values())}，其中含垃圾焚烧关键词 {n_wte}")
print(f"{'均分/满分25':>10} {'条数':>5}  {'垃圾焚烧':<8} 题型")
for avg, n, t, w in rows:
    print(f"{avg:>10.1f} {n:>5}  {'是' if w else '否':<8} {t}")

print()
print("=" * 100)
print("② 焚烧测试 18 题：题型 × 评分")
print("=" * 100)
q = WS / "焚烧测试" / "wte_test_questions.jsonl"
jd = {r["id"]: r for r in load(WS / "焚烧测试" / "wte_v5_judged.jsonl")}
qrows = []
for r in load(q):
    i = r["id"]
    rb = (jd.get(i) or {}).get("rubric", {})
    qrows.append((rb.get("overall", 0), rb.get("correctness", 0), rb.get("boundary", 0),
                  len(rb.get("fabrications", []) or []), r.get("split", ""),
                  (r.get("metadata") or {}).get("group", ""), i, " ".join(r["question"].split())[:60]))
qrows.sort(key=lambda x: (-x[0], x[3]))
print(f"{'总分':>4} {'正确':>4} {'边界':>4} {'编造':>4}  {'split':<8}{'group':<22}{'id':<12} 题目")
for ov, co, bo, fab, sp, grp, i, qs in qrows:
    print(f"{ov:>4} {co:>4} {bo:>4} {fab:>4}  {sp:<8}{grp:<22}{i:<12} {qs}")
