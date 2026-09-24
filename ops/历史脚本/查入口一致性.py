#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""边界一致性：同一件事，GET 入口校验了、POST 入口是否也校验？

已确认一例：GET /hybrid_search?report=photo 明确 400「需要上传图片」，
但 POST 那条路 report=photo 没带图时会怎样？本脚本把这类"入口之间不一致"一次问清。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011"


def call(method, path, data=None, timeout=240):
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
        d = {}
    print("─" * 76)
    print("%s\n  → HTTP %s" % (label, st))
    if "detail" in d:
        print("  detail : %s" % str(d["detail"])[:150])
    else:
        print("  route  : %r   sources=%d" % (d.get("route"), len(d.get("sources") or [])))
        print("  answer : %s" % (d.get("answer") or "")[:130].replace("\n", " "))


print("=" * 76)
print("A. report=photo 但不带图片 —— GET 与 POST 是否一致？")
show("GET  /hybrid_search?query=看看这张现场照片&report=photo", "GET",
     "/hybrid_search?query=%E7%9C%8B%E7%9C%8B%E8%BF%99%E5%BC%A0%E7%8E%B0%E5%9C%BA%E7%85%A7%E7%89%87&report=photo")
show("POST /hybrid_search {query, report:photo}（无 image）", "POST", "/hybrid_search",
     {"query": "看看这张现场照片有什么问题", "report": "photo"})
show("POST /hybrid_search {report:photo}（无 query 无 image）", "POST", "/hybrid_search",
     {"report": "photo"})

print("\n" + "=" * 76)
print("B. history 字段畸形是否被挡")
show("POST {query, history:'不是列表'}", "POST", "/hybrid_search",
     {"query": "危险废物怎么贮存", "history": "不是列表"})
show("POST {query, history:[{role:'xxx'}]}（role 非法）", "POST", "/hybrid_search",
     {"query": "危险废物怎么贮存", "history": [{"role": "xxx", "content": "坏角色"}]})

print("\n" + "=" * 76)
print("C. 超长 query（长度上限是否存在）")
show("POST {query: 5000 字}", "POST", "/hybrid_search", {"query": "危" * 5000})
