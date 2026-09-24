#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把回填报告与缺口清单对照：补回字数 占 缺口字数 的比例是多少。

槽位填充率会低估效果 —— 小图（公式、符号）未填不影响内容，
真正要看的是"缺口字数补回了多少"。
"""
import json
import sys

targets = {t["rel"]: t for t in json.load(open(sys.argv[1] if len(sys.argv) > 1
                                                else "/tmp/回填清单.json", encoding="utf-8"))}
report = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "/tmp/probe.json", encoding="utf-8"))

tot_gap = tot_added = tot_md = 0
rows = []
for r in report:
    if r.get("status") != "ok":
        continue
    t = targets.get(r["rel"])
    if not t:
        continue
    gap = max(t["gap"], 0)
    added = max(r["md_after"] - r["md_before"], 0)   # 内联回填 + 段落差集追加，统一口径
    tot_gap += gap
    tot_added += added
    tot_md += r["md_before"]
    rows.append((gap, added, r["refs"], r["filled"], r.get("appended", 0),
                 r["md_after"], t["pdf_chars"], r["rel"]))

rows.sort(key=lambda x: -x[0])
print(f"{'缺口':>8} {'补回':>8} {'补回率':>7} {'补后/md':>9} {'超PDF':>7} {'槽位':>9} {'追加段':>7}  文档")
over = 0
for gap, added, refs, filled, ap_, after, pdfc, rel in rows:
    rate = f"{100.0*added/gap:.0f}%" if gap > 0 else "n/a"
    ratio = f"{100.0*after/max(pdfc,1):.0f}%"
    excess = after - pdfc
    mark = ""
    if excess > 0:
        over += 1
        mark = f"{excess:+,d}"
    print(f"{gap:8,d} {added:8,d} {rate:>7} {ratio:>9} {mark:>7} {filled:4d}/{refs:<4d} {ap_:7d}  {rel[:44]}")
print(f"\n补后字数超过 PDF 文本字数的文档: {over} / {len(rows)}"
      f"  （超过说明有重复内容被追加）")
print(f"\n合计：缺口 {tot_gap:,} 字，补回 {tot_added:,} 字 "
      f"({100.0*tot_added/max(tot_gap,1):.1f}%)；原文合计 {tot_md:,} 字")
