#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位重排服务 400 的成因：从短到长、从少到多逐步加压，找出触发条件。"""
import json
import urllib.request

URL = "http://127.0.0.1:34005/v1/rerank"
MODEL = "BGE-RERANK-V2-M3"
Q = "大气环境影响评价的评价等级是怎么判定的？"


def call(docs, model=MODEL, query=Q):
    body = json.dumps({"model": model, "query": query, "documents": docs}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        return f"OK  results={len(d.get('results', []))}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        return f"HTTP {e.code}: {detail}"
    except Exception as e:
        return f"{e.__class__.__name__}: {e}"


short = "评价等级按表2的分级判据划分。"
cases = [
    ("1 条短文本", [short]),
    ("2 条短文本", [short, "另一条无关内容"]),
    ("1 条 900 字", ["甲" * 900]),
    ("1 条 1500 字", ["乙" * 1500]),
    ("1 条 3000 字", ["丙" * 3000]),
    ("20 条 900 字", ["丁" * 900] * 20),
    ("20 条 300 字", ["戊" * 300] * 20),
    ("空文档", [""]),
    ("含控制字符", ["正常文本\x00带空字节"]),
]
for name, docs in cases:
    print(f"{name:16s} → {call(docs)}")

print("\n模型名变体测试:")
for m in (MODEL, "bge-reranker-v2-m3", "BGE-RERANKER-V2-M3"):
    print(f"  {m:24s} → {call([short], model=m)}")
