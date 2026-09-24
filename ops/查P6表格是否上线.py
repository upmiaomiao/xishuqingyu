#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6（2026-09-16）的表格修复到底上了线没有？—— 直接找"限值数字"。

P6 记录里影子索引能答出「储油库 NMHC ≤25 g/m³、处理效率 ≥95%」。
那就用这两个数字当探针：哪份语料/索引里有它们，哪份没有。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 储油库 GB 20950—2020 表1 的限值（P6 实测影子索引能答出的那两个数）
PATS = {
    "≤25 或 25 g/m3": re.compile(r"(≤\s*25|25\s*(?:g|mg)\s*/\s*m|25\s*g/m)"),
    "≥95% 处理效率": re.compile(r"(≥\s*95|95\s*%)"),
}
BAD_TITLE = 0


def scan_bundles(name: str) -> None:
    root = Path(f"/data/fagui_rag/{name}")
    if not root.is_dir():
        print(f"  【{name}】不存在")
        return
    files = [p for p in root.rglob("*.md") if "储油库大气污染物排放标准" in p.name]
    print(f"  【{name}】GB 20950 相关 md {len(files)} 份")
    for p in sorted(files)[:3]:
        t = p.read_text(encoding="utf-8", errors="replace")
        img = t.count("images/")
        flags = "  ".join(f"{k}={'有' if v.search(t) else '无'}" for k, v in PATS.items())
        print(f"      {p.name[:52]:<54} 死链图片 {img:>3} 处　{flags}")
        if PATS["≤25 或 25 g/m3"].search(t):
            m = PATS["≤25 或 25 g/m3"].search(t)
            print(f"          …{re.sub(chr(10), ' ', t[max(0, m.start()-70):m.start()+70])}…")


def scan_index(name: str) -> None:
    f = Path(f"/data/fagui_rag/{name}/chunks.jsonl")
    if not f.is_file():
        print(f"  【{name}】没有 chunks.jsonl")
        return
    global BAD_TITLE
    n_oil = n_num = 0
    sample = None
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if "储油库" not in line:
                continue
            c = json.loads(line)
            src = str(c.get("source") or "")
            if not isinstance(c.get("title"), str):
                BAD_TITLE += 1
            if "储油库大气污染物排放标准" not in src and "储油库大气污染物排放标准" not in str(c.get("title")):
                continue
            n_oil += 1
            t = str(c.get("text") or "")
            if PATS["≤25 或 25 g/m3"].search(t) or PATS["≥95% 处理效率"].search(t):
                n_num += 1
                if sample is None:
                    sample = t
    print(f"  【{name}】储油库标准块 {n_oil} 条，含限值数字的 {n_num} 条")
    if sample:
        print(f"      例：{re.sub(chr(10), ' ', sample)[:170]}")


print("① 语料 md（原文树）：")
# 2026-09-22：加上 P6 上线用的两棵树 —— okf_bundles_p6 是"线上语料 + 表格回填"，
# index_p6 是"用 P6 版 ingest 重切"后的新索引；旧的两棵留着做对照（一眼看出差在哪）。
for b in ("okf_bundles", "okf_bundles_p6", "okf_bundles_stage"):
    scan_bundles(b)
print("\n② 索引块文本：")
for i in ("index", "index_p6", "index_stage"):
    scan_index(i)
print(f"\n（附）title 字段不是字符串的脏数据：{BAD_TITLE} 条")
