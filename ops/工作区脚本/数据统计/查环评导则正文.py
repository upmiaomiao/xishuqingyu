#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确核对：环评核心导则的**正文**在不在索引里，以及"公告 vs 正文"的比例。

用法：python 查环评导则正文.py [/data/fagui_rag/index/chunks.jsonl]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

SRC = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index/chunks.jsonl"

docs: dict[str, dict] = {}
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        s = c.get("source", "")
        d = docs.setdefault(s, {"title": c.get("title", ""), "sid": c.get("standard_id") or "",
                                "corpus": s.split("/")[0], "tags": " ".join(c.get("tags") or []),
                                "chars": 0})
        d["chars"] += len(c.get("text") or "")

# 1) 标题含「环境影响评价技术导则」的，区分公告与正文
guide = [(s, d) for s, d in docs.items() if "环境影响评价技术导则" in d["title"]]
notice = [(s, d) for s, d in guide if d["title"].startswith("关于发布")]
real = [(s, d) for s, d in guide if not d["title"].startswith("关于发布")]
print(f"=== 标题含「环境影响评价技术导则」共 {len(guide)} 份 ===")
print(f"    其中【发布公告】{len(notice)} 份、【疑似正文】{len(real)} 份")
print("    --- 疑似正文（按正文长度）---")
for s, d in sorted(real, key=lambda x: -x[1]["chars"])[:25]:
    sid = f" [{d['sid']}]" if d["sid"] else ""
    print(f"      {d['chars']:7d} 字  {d['title'][:60]}{sid}")
print()

# 2) 核心导则编号逐个点名
CORE = ["HJ 2.1", "HJ 2.2", "HJ 2.3", "HJ 2.4", "HJ 610", "HJ 611", "HJ 964", "HJ 1301"]
print("=== 核心导则编号点名 ===")
blob_all = {s: f"{s} {d['title']} {d['tags']} {d['sid']}" for s, d in docs.items()}
for k in CORE:
    hit = [s for s, b in blob_all.items() if k in b]
    kind = []
    for s in hit:
        t = docs[s]["title"]
        kind.append("公告" if t.startswith("关于发布") else ("正文?" if len(t) < 40 else t[:28]))
    print(f"    {k:8s} 命中 {len(hit):2d} 份  {kind}")

# 3) 环评分类管理名录 / 编制监督管理办法 等制度性文件
print()
print("=== 关键制度性文件是否在库 ===")
for kw in ("建设项目环境影响评价分类管理名录", "环境影响评价分类管理名录",
           "建设项目环境影响报告书（表）编制监督管理办法", "环境影响评价法",
           "建设项目环境保护管理条例", "环境影响后评价"):
    hit = [s for s, b in blob_all.items() if kw in b]
    print(f"    {kw:34s} {len(hit)} 份")
    for s in hit[:3]:
        print(f"        · {docs[s]['title'][:56]}  （正文 {docs[s]['chars']} 字）")

# 4) 环评报告本体
rep = [s for s in docs if "环评md" in s or "/环评" in s]
print()
print(f"=== 环评报告本体（报告书/报告表）入库数：{len(rep)} ===")
print("    索引里的顶层目录：", dict(Counter(s.split('/')[0] for s in docs)))

# 5) 同名重复（同一标题多个 source）
print()
dup = Counter(d["title"] for d in docs.values() if d["title"])
reps = {t: n for t, n in dup.items() if n > 1}
print(f"=== 同名重复文档：{len(reps)} 组，重复出的多余份数 {sum(n-1 for n in reps.values())} ===")
for t, n in Counter({t: n for t, n in reps.items()}).most_common(8):
    print(f"    {n} 份  {t[:60]}")
