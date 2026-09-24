#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把"哪些问题能用、哪些 502"分清楚 —— 判断是全局不可用还是只影响专业检索通道。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011"

QS = [
    ("科普/常识类", "什么是环境影响评价？"),
    ("专业法规类", "排污许可证的有效期是多久？"),
    ("专业标准类", "GB 18599 对一般工业固体废物贮存有什么要求？"),
    ("纯聊天类", "你好，你能做什么？"),
]

for label, q in QS:
    body = json.dumps({"query": q}, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + "/hybrid_search", data=body,
                               headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            st, b = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        st, b = e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        st, b = -1, str(e).encode()
    try:
        d = json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        d = {}
    print("─" * 76)
    print("%s：%s" % (label, q))
    print("  HTTP %s  route=%s  sources=%d" % (st, d.get("route"), len(d.get("sources") or [])))
    if st != 200:
        print("  detail: %s" % str(d.get("detail"))[:220])
    else:
        print("  answer: %s" % (d.get("answer") or "")[:110].replace("\n", " "))
