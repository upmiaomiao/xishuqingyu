#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计检索库里"环评相关"的文档：标准/导则/名录/法规有哪些、来自哪个语料。

用法：python 查环评相关文档.py [/data/fagui_rag/index/chunks.jsonl]
输出：文档级命中数、关键词分布、按语料分布、代表性标题。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index/chunks.jsonl"

# 关键词分三组：明确的环评技术标准、环评制度性文件、泛化词（易误命中，单列）
STRICT = ("环境影响评价", "环境影响报告", "环评", "规划环境影响")
GUIDE = ("HJ 2.1", "HJ 2.2", "HJ 2.3", "HJ 2.4", "HJ 610", "HJ 611", "HJ 964",
         "HJ 1301", "HJ 1302", "HJ 1303", "HJ 1304", "HJ 1305", "HJ 1306",
         "HJ 349", "HJ 453", "HJ 616", "HJ 651", "HJ 705", "HJ 953",
         "导则", "技术导则")
SYSTEM = ("分类管理名录", "环境影响评价法", "建设项目环境保护管理条例",
          "竣工环境保护验收", "环境影响后评价", "公众参与", "登记表", "报告表", "报告书")
HINT = ("环境准入", "三线一单", "重大变动", "未批先建")

docs: dict[str, dict] = {}
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        s = c.get("source", "")
        d = docs.setdefault(s, {
            "title": c.get("title", ""), "corpus": s.split("/")[0],
            "type": c.get("type", ""), "standard_id": c.get("standard_id") or "",
            "tags": " ".join(c.get("tags") or []), "chunks": 0,
        })
        d["chunks"] += 1

print(f"索引文档总数：{len(docs)}")
print("按语料：", dict(Counter(d["corpus"] for d in docs.values())))
print("按类型：", dict(Counter(d["type"] for d in docs.values())))
print()

def hit(keywords):
    out = []
    for s, d in docs.items():
        blob = f"{s} {d['title']} {d['tags']} {d['standard_id']}"
        if any(k in blob for k in keywords):
            out.append((s, d))
    return out

groups = [("① 环评明确相关（标题/路径/标签含「环评」「环境影响」）", STRICT),
          ("② 环评技术标准与导则（HJ 2.x / HJ 6xx / 导则）", GUIDE),
          ("③ 环评制度性文件（名录/评价法/条例/验收/公众参与）", SYSTEM),
          ("④ 相关概念（环境准入/三线一单/重大变动/未批先建）", HINT)]

seen_all: set[str] = set()
for label, kws in groups:
    hits = hit(kws)
    for s, _ in hits:
        seen_all.add(s)
    print(f"=== {label} → {len(hits)} 份 ===")
    print("    按语料：", dict(Counter(d["corpus"] for _, d in hits)))
    for s, d in sorted(hits, key=lambda x: x[1]["title"])[:14]:
        sid = f" [{d['standard_id']}]" if d["standard_id"] else ""
        print(f"      · {d['title'][:56]}{sid}")
    if len(hits) > 14:
        print(f"      …（还有 {len(hits)-14} 份）")
    print()

print(f"四组去重后合计：{len(seen_all)} 份（占索引 {len(seen_all)/len(docs)*100:.1f}%）")
print()
# 反向确认：环评报告本体是否入库
rep = [s for s in docs if "环评" in s and ("md/md" in s or "环评md" in s)]
print(f"疑似「环评报告本体」（路径含 环评md）：{len(rep)} 份")
print("索引里出现的顶层目录：", dict(Counter(s.split('/')[0] for s in docs)))
