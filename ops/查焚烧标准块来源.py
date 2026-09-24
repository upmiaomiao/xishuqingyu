#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查清：索引里含「生活垃圾焚烧污染控制标准 / GB 18485」的块，是标准本体还是别处引用。

判断依据：title、doc_type、source 路径。若全部来自环评报告/通知，则说明
**标准本体不在语料里**，焚烧限值只能从二手引用里拿。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")
KEYS = ("生活垃圾焚烧污染控制标准", "18485")

hits = []
with IDX.open(encoding="utf-8") as f:
    for line in f:
        if not any(k in line for k in KEYS):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        hits.append(d)

print(f"含关键词的块：{len(hits)}")
print("\n按 doc_type：", dict(Counter(d.get("doc_type") or "?" for d in hits)))
print("\n按 title 归类（前 15）：")
for t, c in Counter(d.get("title") or "?" for d in hits).most_common(15):
    print(f"  {c:>5}  {t[:90]}")

print("\n按 source 顶层目录：")
for t, c in Counter((d.get("source") or "?").split("/")[0] for d in hits).most_common():
    print(f"  {c:>5}  {t}")

print("\n是否有一篇文档『标题就叫』生活垃圾焚烧污染控制标准：")
own = [d for d in hits if "生活垃圾焚烧污染控制标准" in (d.get("title") or "")]
print(f"  标题含该字样的块：{len(own)}")
for t, c in Counter(d.get("title") for d in own).most_common(10):
    print(f"   {c:>5}  {t}")

print("\n抽样 4 条看正文（判断是限值表还是转述）：")
for d in hits[:4]:
    txt = " ".join((d.get("text") or "").split())[:220]
    print(f"\n  ▸ title={d.get('title')}\n    doc_type={d.get('doc_type')} standard_id={d.get('standard_id')}"
          f"\n    source={d.get('source')}\n    text={txt}")
