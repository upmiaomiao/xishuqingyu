#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稀释是否造成"专业性错误"：看线上对标准数值问题的实际回答。

关键区分：
  · 答"资料不足" —— 能力不足，但不误导；
  · 拿报告里的项目实测值当标准限值答 —— **专业错误**，会误导用户。
"""
import json
import urllib.request

BASE = "http://127.0.0.1:8011"
QS = [
    "生活垃圾焚烧烟气中二噁英的排放限值是多少？",
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
]


def ask(q):
    body = json.dumps({"query": q, "top_k": 5}).encode()
    req = urllib.request.Request(BASE + "/hybrid_search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


for q in QS:
    print("=" * 78)
    print("问：", q)
    d = ask(q)
    print(f"路由：{d.get('route')}  引用 {len(d.get('sources') or [])} 条")
    for s in (d.get("sources") or [])[:5]:
        print(f"  - {s.get('title','')[:34]} | {s.get('source','')[:64]}")
    print("\n答案：")
    print((d.get("answer") or "")[:900])
