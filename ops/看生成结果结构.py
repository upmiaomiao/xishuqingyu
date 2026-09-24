#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼生成结果 JSON 的结构（C9 验收用：叙述/措施概述到底在哪个键下）。"""
import json
import sys

for p in sys.argv[1:]:
    print("=" * 70)
    print(p)
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        print("  读不了：%s" % exc)
        continue
    if not isinstance(d, dict):
        print("  顶层不是 dict：%s" % type(d))
        continue
    print("  顶层键：%s" % list(d))
    for k, v in d.items():
        if isinstance(v, dict):
            print("  %s → dict 键：%s" % (k, list(v)[:14]))
        elif isinstance(v, list):
            print("  %s → list %d 项" % (k, len(v)))
        else:
            print("  %s → %s" % (k, str(v)[:100]))
    # 全文搜一遍关键词，避免漏看
    s = json.dumps(d, ensure_ascii=False)
    for kw in ("措施概述", "跳过原因", "措施名无出处", "剔除", "折合", "narr-v"):
        print("  含「%s」：%s" % (kw, kw in s))
