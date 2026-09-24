#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按序号打印某份文档的回填明细（含未填原因）。用法：看单份.py /tmp/probe.json <序号> [清单]"""
import json
import sys

rep = json.load(open(sys.argv[1], encoding="utf-8"))
idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
tl = sys.argv[3] if len(sys.argv) > 3 else None
if tl:
    targets = json.load(open(tl, encoding="utf-8"))
    order = [t["rel"] for t in sorted(targets, key=lambda x: -x["gap"])]
    rel = order[idx]
    rep = [r for r in rep if r["rel"] == rel]
rep.sort(key=lambda r: -r.get("gap", 0))
for r in rep[: idx + 1] if not tl else rep:
    print(f"文档: {r['rel'][:80]}")
    print(f"  状态 {r['status']}  缺口 {r.get('gap'):,}  原文 {r.get('md_before'):,} → {r.get('md_after'):,}")
    print(f"  图片引用 {r.get('refs')}  簇 {r.get('slots')}  已回填 {r.get('filled')}  "
          f"新增 {r.get('added'):,} 字  回退定位 {r.get('fallback')}")
    print(f"  未填原因: {r.get('why')}")
    if r.get("reason"):
        print(f"  跳过原因: {r['reason']}")
    print()
    break
