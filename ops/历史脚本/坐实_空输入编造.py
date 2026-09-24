#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""坐实缺陷②：POST /hybrid_search 空输入不被拦，落到「请说明这张图片的内容」兜底 →
模型凭空编造一段"图片描述"并以 200 返回。逐条对照三个入口的校验是否一致。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def call(method, path, data=None, timeout=180):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    h = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode()


def show(label, method, path, data=None):
    st, b = call(method, path, data)
    try:
        d = json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        d = None
    print("─" * 76)
    print("%s\n  → HTTP %s" % (label, st))
    if isinstance(d, dict):
        if "detail" in d:
            print("  detail: %s" % d["detail"])
        else:
            ans = (d.get("answer") or "")
            print("  query=%r route=%r image_note=%r" % (d.get("query"), d.get("route"), d.get("image_note")))
            print("  answer 长度 %d：%s" % (len(ans), ans[:180].replace("\n", " ")))
    else:
        print("  body: %s" % b[:160])
    return st, d


print("=" * 76)
print("同一件事（空输入）在三个入口的待遇：")
show("① POST /hybrid_search  body={}          （非流式）", "POST", "/hybrid_search", {})
show("② POST /hybrid_search  body={'query':''} ", "POST", "/hybrid_search", {"query": ""})
show("③ POST /hybrid_search  body={'query':'   '}（全空格）", "POST", "/hybrid_search", {"query": "   "})
show("④ POST /hybrid_search/stream body={}   （流式，有前置校验）", "POST", "/hybrid_search/stream", {})
show("⑤ GET  /hybrid_search?query=           （有 min_length=1）", "GET", "/hybrid_search?query=")

print("\n" + "=" * 76)
print("对照：有真实问题时是正常的（证明不是模型坏了）")
show("⑥ POST /hybrid_search {'query':'生活垃圾焚烧飞灰是否属于危险废物'}",
     "POST", "/hybrid_search", {"query": "生活垃圾焚烧飞灰是否属于危险废物"})
