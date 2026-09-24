#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""问一题：给定站点与问题，打印答案 + 命中情况（上线后真机抽查用）。

用法：/home/test/fagui_serve/.venv/bin/python 问一题.py <base> <关键词1,关键词2> <问题>
"""
from __future__ import annotations

import json
import sys
import urllib.request


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011"
    needles = [x for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else []) if x]
    q = sys.argv[3] if len(sys.argv) > 3 else "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？"
    req = urllib.request.Request(
        base.rstrip("/") + "/hybrid_search",
        data=json.dumps({"query": q}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=900).read().decode("utf-8"))
    ans = d.get("answer") or ""
    srcs = d.get("sources") or []
    print("站点：%s" % base)
    print("问题：%s" % q)
    print("命中：%s" % {n: (n in ans) for n in needles})
    print("引用 %d 条：" % len(srcs))
    for s in srcs[:6]:
        print("   · %s ｜ %s" % (s.get("standard_id") or "", str(s.get("title") or "")[:44]))
    print("答案：%s" % ans[:700].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
