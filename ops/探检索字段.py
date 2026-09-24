#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[025] 定位：问答线的检索命中里到底带不带 status_note。

两路取证：
  ① 静态：读 /data/fagui_rag/retriever.py，看 hit/meta 的字段白名单里有没有 status_note；
  ② 动态：真机问一句"固废法还能用吗"，打印返回的 sources[0] 的全部键与 status/status_note。
只读，不改任何东西。
"""
from __future__ import annotations

import io
import json
import re
import urllib.request

RETRIEVER = "/data/fagui_rag/retriever.py"
SITE = "http://127.0.0.1:8011/hybrid_search"
Q = "《中华人民共和国固体废物污染环境防治法》现在还能用吗？"


def main() -> int:
    print("==== ① 静态：retriever.py 的字段拼装 ====")
    t = io.open(RETRIEVER, encoding="utf-8", errors="ignore").read()
    print("  文件 %d 行；出现次数：status=%d  status_note=%d  standard_id=%d  doc_type=%d"
          % (t.count("\n") + 1, t.count('"status"') + t.count("'status'"),
             t.count("status_note"), t.count("standard_id"), t.count("doc_type")))
    for m in re.finditer(r"^.*(?:standard_id|doc_type|status_note|\"status\").*$", t, re.M):
        ln = t[:m.start()].count("\n") + 1
        line = m.group(0).strip()
        if len(line) > 150:
            line = line[:150] + "…"
        print("   %-5d %s" % (ln, line))

    print("\n==== ② 动态：真机返回的 sources 字段 ====")
    req = urllib.request.Request(SITE, data=json.dumps({"query": Q}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=900).read().decode("utf-8"))
    srcs = d.get("sources") or []
    print("  引用 %d 条" % len(srcs))
    for i, s in enumerate(srcs[:4], 1):
        print("   [%d] 键：%s" % (i, sorted(s.keys())))
        print("       title=%s" % str(s.get("title"))[:60])
        print("       status=%r  status_note=%r" % (s.get("status"),
                                                    str(s.get("status_note"))[:90]))
    keys = set()
    for s in srcs:
        keys |= set(s.keys())
    print("\n  全部引用里出现过的键：%s" % sorted(keys))
    print("  → status_note 是否出现在接口返回里：%s" % ("是" if "status_note" in keys else "否 ✗"))
    print("\n  答案开头：%s" % (d.get("answer") or "")[:120].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
