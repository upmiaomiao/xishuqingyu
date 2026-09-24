#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：从线上索引导出"带时效状态/依据的材料清单"（A2 标准现行性底稿的事实来源）。

为什么要从索引导、不手写：这批状态是我 2026-09-22 改的，散在 29 份 bundle 的 front matter 里；
手抄一遍必然与线上漂移。这里直接读**线上正在用的** chunks.jsonl 归并，输出 JSON。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 导出状态清单.py [索引目录]
输出：/tmp/状态清单.json  （stdout 只打摘要）
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter

d = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index"
by_src: dict = {}
n = 0
with io.open(d + "/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        n += 1
        try:
            o = json.loads(line)
        except Exception:
            continue
        src = o.get("source") or ""
        st = (o.get("status") or "").strip()
        note = (o.get("status_note") or "").strip()
        # 只看**写了依据**的行：全库有一大批材料带 status 字段（语料原始标注），
        # 那是另一回事；A2 关心的是"我们给出废止/替代依据"的这批（692 行 / 29 份）。
        if not note:
            continue
        e = by_src.setdefault(src, {"source": src, "块数": 0, "status": Counter(),
                                    "status_note": Counter(), "title": "",
                                    "standard_id": "", "doc_type": ""})
        e["块数"] += 1
        e["status"][st or "(空)"] += 1
        if note:
            e["status_note"][note] += 1
        for k in ("title", "standard_id", "doc_type"):
            if not e[k] and o.get(k):
                e[k] = str(o.get(k))

rows = []
for src, e in sorted(by_src.items()):
    rows.append({
        "source": src,
        "title": e["title"],
        "standard_id": e["standard_id"],
        "doc_type": e["doc_type"],
        "块数": e["块数"],
        "status": dict(e["status"]),
        "status_note": (sorted(e["status_note"], key=lambda k: -e["status_note"][k]) or [""])[0],
    })

out = "/tmp/状态清单.json"
with io.open(out, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

print("索引 %s 共 %d 块；带状态/依据的材料 %d 份 → %s" % (d, n, len(rows), out))
print()
print("%-3s %-8s %-10s %-6s %s" % ("#", "块数", "doc_type", "标准号", "名称 / 依据"))
for i, r in enumerate(rows, 1):
    print("%-3d %-8d %-10s %-6s %s" % (i, r["块数"], r["doc_type"][:9], r["standard_id"][:6],
                                       (r["title"] or r["source"].split("/")[-1])[:56]))
    if r["status_note"]:
        print("      └ %s" % r["status_note"][:104])
