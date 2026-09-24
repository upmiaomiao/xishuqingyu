#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查清 4 个失败是"图谱里没有"还是"我的匹配有问题"。

失败项：
  ① 颗粒物 / 二氧化硫 没被识别
  ② GB 18597-2023 相关标准没被识别
  ③④ 名字重叠去重没被触发（我的测试文本里根本没有长名字的完整形式）
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def search(q: str, depth: int = 0, limit: int = 70):
    with urllib.request.urlopen(
        BASE + "/kg/search?query=%s&depth=%d&limit=%d" % (urllib.parse.quote(q), depth, limit),
        timeout=60,
    ) as r:
        return json.loads(r.read().decode("utf-8"))


print("=" * 92)
print("① 图谱里到底有没有「颗粒物」「二氧化硫」")
print("=" * 92)
for q in ["颗粒物", "二氧化硫", "氮氧化物", "危险废物", "贮存"]:
    d = search(q)
    hits = [(n["name"], n["label"]) for n in d.get("nodes", []) if n.get("matched")]
    print("  %-10s → %d 个命中" % (q, len(hits)))
    for nm, lb in hits[:6]:
        print("        [%s] %s" % (lb, nm))

print()
print("=" * 92)
print("② 图谱里的污染物（Pollutant）都叫什么")
print("=" * 92)
d = search("污染物", depth=1, limit=70)
polls = [n for n in d.get("nodes", []) if n.get("label") == "Pollutant"]
print("  这一子图里的污染物 %d 个：" % len(polls))
for n in polls[:25]:
    print("        %s   (props: %s)" % (n["name"], n.get("props", {})))

print()
print("=" * 92)
print("③ 有没有名字里带 18597 的标准")
print("=" * 92)
for q in ["18597", "危险废物贮存污染控制标准", "GB 18597"]:
    d = search(q)
    hits = [(n["name"], n["label"], (n.get("props") or {}).get("std_id", ""))
            for n in d.get("nodes", []) if n.get("matched")]
    print("  搜「%s」→ %d 个命中" % (q, len(hits)))
    for nm, lb, sid in hits[:6]:
        print("        [%s] %s  std_id=%s" % (lb, nm, sid))

print()
print("=" * 92)
print("④ 长名字是否真的存在于图谱（去重逻辑的前提）")
print("=" * 92)
for q in ["中华人民共和国固体废物污染环境防治法", "固体废物污染环境防治法", "固体废物"]:
    d = search(q)
    hits = [(n["name"], n["label"]) for n in d.get("nodes", []) if n.get("matched")]
    print("  搜「%s」→ %d 个命中：%s" % (q, len(hits), [h[0] for h in hits[:4]]))
