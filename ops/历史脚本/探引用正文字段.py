#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探一次 /hybrid_search：看 sources 里到底有哪些字段（尤其有没有引用正文）。"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://10.201.31.10:8011"
q = "生活垃圾焚烧飞灰稳定化处理应满足哪些要求？"

req = urllib.request.Request(BASE + "/hybrid_search",
                             data=json.dumps({"query": q}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=600) as r:
    d = json.loads(r.read().decode())

print("顶层字段：", list(d.keys()))
for k, v in d.items():
    if k in ("sources", "answer"):
        continue
    print(f"  {k} = {str(v)[:200]}")
srcs = d.get("sources") or []
print(f"\nsources：{len(srcs)} 条；每条字段 = {list(srcs[0].keys()) if srcs else '—'}")
for s in srcs[:3]:
    print("-" * 90)
    for k, v in s.items():
        t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        t = " ".join(t.split())
        print(f"   {k:<12}{t[:400]}")
print("\n答案前 200 字：", " ".join((d.get('answer') or '').split())[:200])
