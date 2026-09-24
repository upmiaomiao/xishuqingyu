#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现线上重排请求，打印服务端 400 的具体原因。"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever  # noqa: E402

Q = sys.argv[1] if len(sys.argv) > 1 else "大气环境影响评价的评价等级是怎么判定的？"

r = Retriever()
qv = r.embed(Q)
hits = r.search(qv, top_k=20)
cands = [(i, s, r.chunks[i]) for i, s in hits]
docs = [c[2]["text"] for c in cands]

print(f"候选 {len(docs)} 条；长度分布: min={min(map(len, docs))} max={max(map(len, docs))}")
print("文档类型:", {type(d).__name__ for d in docs})

body = json.dumps({"model": "BGE-RERANK-V2-M3", "query": Q, "documents": docs}).encode()
req = urllib.request.Request("http://127.0.0.1:34005/v1/rerank", data=body,
                            headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("OK", len(json.loads(resp.read().decode())["results"]))
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")

# 逐条二分：找出哪一条会导致 400
print("\n逐条单独发送（找出问题文档）:")
bad = []
for i, d in enumerate(docs):
    b = json.dumps({"model": "BGE-RERANK-V2-M3", "query": Q, "documents": [d]}).encode()
    rq = urllib.request.Request("http://127.0.0.1:34005/v1/rerank", data=b,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        bad.append(i)
        print(f"  [{i}] HTTP {e.code}: {detail}")
        print(f"      文本前 120 字: {d[:120]!r}")
        print(f"      长度 {len(d)}  含空字节={chr(0) in d}  含代理字符="
              f"{any(0xD800 <= ord(ch) <= 0xDFFF for ch in d)}")
if not bad:
    print("  逐条都通过 → 问题在组合（数量/总长度）")
