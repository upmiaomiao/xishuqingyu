#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：看清《污水综合排放标准》在库里到底有几份、什么状态、规则原文在哪一份里。

为什么必须先看这个（B5）：探针查到库里有两组 8978 相关的块，
一组 30 块却标着「已废止」、一组只有 2 块标「现行」。
检索器对「已废止」是**扣 0.35 分**的，所以"哪一份是现行版、规则原文在哪一份"
直接决定修法：要是规则只在已废止那份里，就不能简单靠提权把它顶上来，
得先弄清那份是不是真的废止（年份/版本），否则等于拿废止文本当现行依据。
"""
from __future__ import annotations

import io
import re
import sys

sys.path.insert(0, "/data/fagui_rag")
sys.path.insert(0, "/home/test/xishu_qingyu_serve")

from xishu_pipeline.retrieve import retriever                      # noqa: E402
import retriever as R                                               # noqa: E402

HI = re.compile(r"第一类污染物")
WS = re.compile(r"车间")

print("=" * 100)
print("[1] 库里所有与 8978 / 污水综合排放标准 有关的块，按 source 归并")
by: dict = {}
for i, c in enumerate(retriever.chunks):
    src = c.get("source") or ""
    title = c.get("title") or ""
    if not ("8978" in src or "污水综合排放标准" in title or "8978" in title):
        continue
    e = by.setdefault(src, {"n": 0, "hi": 0, "status": set(), "title": title,
                            "sid": c.get("standard_id"), "corpus": R.corpus_of(c),
                            "first_rule": None, "first_idx": None})
    e["n"] += 1
    e["status"].add(c.get("status") or "(空)")
    if HI.search(c.get("text") or "") and WS.search(c.get("text") or ""):
        e["hi"] += 1
        if e["first_rule"] is None:
            e["first_rule"] = (c.get("text") or "")[:400]
            e["first_idx"] = i
for src, e in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
    print("-" * 100)
    print("  路径：%s" % src)
    print("  块数 %-4d ｜ 状态 %s ｜ 标准号 %s ｜ 语料 %s" % (e["n"], "/".join(sorted(e["status"])),
                                                    e["sid"], e["corpus"]))
    print("  标题：%s" % e["title"][:80])
    print("  含「第一类污染物+车间」的块：%d 条" % e["hi"])
    if e["first_rule"]:
        print("  规则原文（块 #%d）：%s" % (e["first_idx"], re.sub(r"\s+", " ", e["first_rule"])))

print("=" * 100)
print("[2] 那份标「已废止」的，status_note 写了什么（判断是否我们改的）")
for src, e in by.items():
    if "已废止" in e["status"]:
        for i, c in enumerate(retriever.chunks):
            if (c.get("source") or "") == src and (c.get("status_note") or ""):
                print("  路径：%s" % src[:90])
                print("  状态依据：%s" % c["status_note"][:220])
                break
        else:
            print("  路径：%s" % src[:90])
            print("  状态依据：（没有 status_note —— 说明不是 2026-09-22 那批改的，是语料自带）")

print("=" * 100)
print("[3] 用「GB8978」当硬条件扫一遍：哪些块的 source/标题里带 8978 这个号")
n = 0
for i, c in enumerate(retriever.chunks):
    sid = str(c.get("standard_id") or "")
    title = c.get("title") or ""
    if re.search(r"8978", sid) or re.search(r"8978", title):
        n += 1
        if n <= 5:
            print("   · standard_id=%-14s status=%-6s %s" % (sid, c.get("status"), title[:60]))
print("  带 8978 号（standard_id 或标题）的块共 %d 条" % n)
