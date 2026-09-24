#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓「发图 + 带文字，但不勾选照片研判」这条路径的事件序列。

为什么单独抓：上一条抓的是 query="" + report=photo 的路径，run/done 是配平的。
但用户很可能就是普通发图（勾选框默认不勾），那是**另一条分支**。
前端只要有一条 run 没有配对的 done，那一步就会永远转圈 —— 这正是用户报的现象。
"""
from __future__ import annotations

import json
import urllib.request
from collections import Counter

BASE = "http://10.201.31.10:8011"
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAHElEQVQoz2NkYPjPQAxg"
       "YhgFo2AUjIJRMApGwSgAAAsSAAGr0n0MAAAAAElFTkSuQmCC")
IMAGE = "data:image/png;base64," + PNG


def ask(query, image, report, label):
    payload = {"query": query, "history": [], "image": image, "report": report}
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("=" * 92)
    print("【%s】query=%r  image=%s  report=%r" % (label, query, "有" if image else "无", report))
    print("=" * 92)
    seq = []
    with urllib.request.urlopen(req, timeout=300) as r:
        ev = data = ""
        for raw in r:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
            elif line == "" and ev:
                try:
                    p = json.loads(data)
                except Exception:                                  # noqa: BLE001
                    p = data
                if ev == "status":
                    seq.append((p.get("stage"), p.get("state")))
                    print("   status  %-10s %-6s %s" % (p.get("stage"), p.get("state"), p.get("message", "")))
                elif ev == "vision":
                    print("   vision  收到 %d 字" % len(str(p.get("text", ""))))
                elif ev == "error":
                    print("   ERROR   %s" % p)
                elif ev == "done":
                    print("   done    route=%s latency=%ss" % (p.get("route"), p.get("latency_s")))
                ev = data = ""

    c = Counter(seq)
    print("   --- run/done 配平 ---")
    unbalanced = []
    for stage in dict.fromkeys(s for s, _ in seq):
        nr, nd = c.get((stage, "run"), 0), c.get((stage, "done"), 0)
        mark = ""
        if nr > nd:
            mark = "  <-- run 比 done 多 %d 个！前端会一直转" % (nr - nd)
            unbalanced.append(stage)
        print("     %-10s run=%-3d done=%-3d%s" % (stage, nr, nd, mark))
    if not unbalanced:
        print("     （全部配平）")
    return unbalanced


print("#" * 92)
print("# 路径一：发图 + 带文字，report=None（普通发图，勾选框默认不勾）")
print("#" * 92)
u1 = ask("这是什么", IMAGE, None, "发图+文字·普通")

print()
print("#" * 92)
print("# 路径二：发图 + 带文字 + report=photo")
print("#" * 92)
u2 = ask("这是什么", IMAGE, "photo", "发图+文字·研判")

print()
print("#" * 92)
print("# 路径三：只发图不打字，report=None")
print("#" * 92)
u3 = ask("", IMAGE, None, "只发图·普通")

print()
print("=" * 92)
print("结论")
print("=" * 92)
bad = {"发图+文字·普通": u1, "发图+文字·研判": u2, "只发图·普通": u3}
any_bad = False
for k, v in bad.items():
    if v:
        any_bad = True
        print("  × %-16s 有未配平的步骤：%s" % (k, "、".join(v)))
    else:
        print("  √ %-16s run/done 全部配平" % k)
if not any_bad:
    print()
    print("  → 三条路径都配平，说明前端一直转**不是**因为后端漏发 done，")
    print("     要回前端找原因（渲染条件、CSS、或 renderMessages 时机）。")
