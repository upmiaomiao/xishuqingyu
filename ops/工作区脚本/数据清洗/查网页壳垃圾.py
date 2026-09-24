#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""识别索引里的「网页导航壳垃圾」：正文很短且含网站导航/版权字样。

这类文件是抓取时把栏目页框架一起存下来的产物，没有任何法规/标准内容，属于**纯噪声**，
占用了检索位。判定用两个条件同时满足（短 + 含导航特征），避免误伤真正的短公告。

用法：python 查网页壳垃圾.py [--list N]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict

SRC = "/data/fagui_rag/index/chunks.jsonl"
SHOW = 20
if "--list" in sys.argv:
    SHOW = int(sys.argv[sys.argv.index("--list") + 1])

NAV = ("当前位置：首页", "网站声明网站地图", "标准发布标准解读标准文本", "中国政府网国务院部门",
       "ICP备案编号", "京公网安备", "字号：[大]", "仅打印内容", "链接 ：全国人大")
SHORT = 1500          # 正文总字数上限

docs: dict[str, dict] = defaultdict(lambda: {"ch": 0, "n": 0, "head": ""})
for line in open(SRC, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    c = json.loads(line)
    d = docs[c["source"]]
    d["ch"] += len(c.get("text") or "")
    d["n"] += 1
    if c.get("chunk_index") == 0:
        d["head"] = (c.get("text") or "")
        d["title"] = c.get("title") or ""
        d["type"] = c.get("type") or ""

junk, borderline = [], []
for s, d in docs.items():
    body_probe = d["head"][:400]
    nav_hits = sum(1 for k in NAV if k in body_probe or k in d["head"])
    if d["ch"] <= SHORT and nav_hits >= 1:
        junk.append((d["ch"], s, d))
    elif nav_hits >= 2:
        borderline.append((d["ch"], s, d))

print(f"索引文档 {len(docs)}")
print(f"=== 网页壳垃圾（正文 ≤{SHORT} 字 且 含导航字样）：{len(junk)} 份，"
      f"共 {sum(x[0] for x in junk)} 字 ===")
for ch, s, d in sorted(junk)[:SHOW]:
    print(f"   {ch:5d}字  {(d.get('title') or '')[:40]:40s} {s[:80]}")
print()
print(f"=== 可疑但正文较长（含 ≥2 处导航字样）：{len(borderline)} 份 ===")
for ch, s, d in sorted(borderline, reverse=True)[:10]:
    print(f"   {ch:6d}字  {(d.get('title') or '')[:40]:40s} {s[:80]}")
print()
print("按语料：", Counter(s.split("/")[0] for _, s, _ in junk))
print("按类型：", Counter(d.get("type") or "(空)" for _, _, d in junk))
