#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：[021] 重跑前后逐项对比（结论有没有变、变在哪）。

为什么不是"看一眼统计数字"：统计（存在问题/疑似/无问题…）可能总量相同而**具体项换了**，
那才是真正需要人看的。所以这里逐项比 审核项 + AI审核 + 依据/说明，并把差异列出来。

用法（服务器）：python 比重跑前后.py ["报告名.json"]
"""
from __future__ import annotations

import io
import json
import os
import sys

OLD = "/home/test/_重构归档_20260922/第三批_前/审核结果_重跑前"
NEW = "/data/eia_audit/_审核结果"

name = sys.argv[1] if len(sys.argv) > 1 else "1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.json"


def load(base: str):
    p = os.path.join(base, name)
    if not os.path.exists(p):
        return None, p
    return json.load(io.open(p, encoding="utf-8")), p


o, op = load(OLD)
n, np_ = load(NEW)
print("旧：%s  %s" % (op, "有" if o else "缺"))
print("新：%s  %s" % (np_, "有" if n else "缺"))
if not (o and n):
    sys.exit(2)

print("\n统计：")
print("  旧 %s" % json.dumps(o.get("统计"), ensure_ascii=False))
print("  新 %s" % json.dumps(n.get("统计"), ensure_ascii=False))
print("  相同：%s" % (o.get("统计") == n.get("统计")))

oi, ni = o.get("items") or [], n.get("items") or []
print("\n条数：旧 %d ／ 新 %d" % (len(oi), len(ni)))

KEY = ("审核项", "环评文件", "AI审核", "依据", "说明", "问题", "建议")


def sig(it):
    """**整条**的签名，不是只看几个字段。

    踩过的坑：第一版只把上面 7 个字段拼成签名，于是"理由文字一字未改、但证据/判据轨迹变了"
    的条目会被判成"完全一致" —— 我当时拿它去复核对账结果，得到"只有 1 条差异"，
    与对账脚本的"4 条差异"矛盾，白查了一轮文件时间戳。比较就要比全部字段。
    """
    return json.dumps(it, ensure_ascii=False, sort_keys=True)


same = 0
diffs = []
for a, b in zip(oi, ni):
    if sig(a) == sig(b):
        same += 1
    else:
        diffs.append((a, b))
print("逐项完全一致：%d ／ 有差异：%d" % (same, len(diffs)))

for a, b in diffs[:12]:
    print("\n--- 差异项：%s ｜ %s ---" % (a.get("审核项"), a.get("环评文件")))
    print("  判定：%s → %s" % (a.get("AI审核"), b.get("AI审核")))
    for k in KEY:
        va, vb = str(a.get(k, "")), str(b.get(k, ""))
        if va != vb:
            print("  %s：" % k)
            print("    旧 %s" % va[:200])
            print("    新 %s" % vb[:200])
    print("  常见字段（依据/说明/问题/建议）是否一致：%s"
          % all(str(a.get(k, "")) == str(b.get(k, "")) for k in ("依据", "说明", "问题", "建议")))
    # 真正找出"到底哪个字段变了"：逐键比全部键，别只比我猜的那几个
    allk = sorted(set(a.keys()) | set(b.keys()))
    ch = [k for k in allk if a.get(k) != b.get(k)]
    print("  该条全部键：%s" % allk)
    print("  变化的键：%s" % ch)
    for k in ch:
        print("    %s 旧：%s" % (k, json.dumps(a.get(k), ensure_ascii=False)[:400]))
        print("    %s 新：%s" % (k, json.dumps(b.get(k), ensure_ascii=False)[:400]))

print("\n顶层字段差异：")
for k in sorted(set(o.keys()) | set(n.keys())):
    if o.get(k) != n.get(k):
        print("  %s：" % k)
        print("    旧 %s" % json.dumps(o.get(k), ensure_ascii=False)[:500])
        print("    新 %s" % json.dumps(n.get(k), ensure_ascii=False)[:500])

print("\n结论：%s" % ("重跑结果与旧结果**逐项一致** → 这次重跑是空转（判据层不经检索、抽取命中缓存）"
                    if not diffs else "重跑结果**有变化**，需要人工逐条看上面的差异"))
