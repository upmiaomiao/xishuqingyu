#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顶层条目地图（修正版）。

prettier 会把闭合括号也放在第 0 列，所以「第 0 列」不足以判定条目起点。
规则：**第 0 列、非空、且不以 } ) ] 开头**的行才是条目起点；
条目范围 = [本条起点, 下一条起点 - 1]。
"""
from __future__ import annotations

import io
import re

P = r"_中间产物/重构工作区/frontend/_app_pretty.js"
lines = io.open(P, encoding="utf-8").read().split("\n")

CLOSE = re.compile(r"^[}\])]")


def is_start(l: str) -> bool:
    return bool(l) and not l[0].isspace() and not CLOSE.match(l)


starts = [i for i, l in enumerate(lines) if is_start(l)]
items = []
for k, s in enumerate(starts):
    e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(lines) - 1
    items.append((s, e))

print("总行数 %d，顶层条目 %d 个" % (len(lines), len(items)))
print()
print("%-10s %-6s %-7s %s" % ("行范围", "行数", "字节", "类型 / 名字"))
print("-" * 100)
named = []
for s, e in items:
    first = lines[s]
    m = re.match(r"(?:export\s+)?(?:async\s+)?function\s+([\w$]+)", first)
    m2 = re.match(r"(?:const|let|var)\s+([\w$]+)", first)
    if m:
        kind, name = "function", m.group(1)
    elif m2:
        kind, name = first.split()[0], m2.group(1)
    else:
        kind, name = "stmt", ""
    named.append((s, e, kind, name))
    label = ("%s %s" % (kind, name)) if name else " ".join(first.split())[:56]
    print("%-10s %-6d %-7d %s" % ("%d-%d" % (s + 1, e + 1), e - s + 1, len("\n".join(lines[s:e + 1]).encode()), label))

# 校验：所有条目首尾相接，正好覆盖全文（除首尾空行）
gap = []
for k in range(len(items) - 1):
    if items[k][1] + 1 != items[k + 1][0]:
        gap.append((items[k][1] + 2, items[k + 1][0]))
print()
print("覆盖校验：条目之间是否无缝")
if gap:
    print("  ✗ 有缝隙：%s" % gap[:5])
else:
    print("  ★ 无缝：条目 %d-%d 连续覆盖" % (items[0][0] + 1, items[-1][1] + 1))
print("  首条目起点行 %d，末条目终点行 %d，文件 %d 行"
      % (items[0][0] + 1, items[-1][1] + 1, len(lines)))
blank_tail = [i + 1 for i, l in enumerate(lines) if not l.strip()]
print("  空行共 %d 行（落在条目内部的空行会被一起带走）" % len(blank_tail))

print()
print("=" * 100)
print("函数清单（按名字）")
print("=" * 100)
fns = [(n, s, e) for s, e, k, n in named if k == "function"]
print("  共 %d 个函数" % len(fns))
for n, s, e in fns:
    print("    %-26s 行 %d-%d（%d 行）" % (n, s + 1, e + 1, e - s + 1))
