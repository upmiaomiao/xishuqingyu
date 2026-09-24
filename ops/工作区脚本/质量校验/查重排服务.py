#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查重排服务是否真的在重排。

做法：用一个查询配三条**相关性差别极大**的文档，看重排分数是否拉开差距。
· 分数明显分层（如 0.9 / 0.1 / 0.01）→ 重排正常；
· 三条都在 0.99 以上且几乎相同 → 重排服务没有区分能力（等于没重排）。
"""
import json
import urllib.request

URL = "http://127.0.0.1:34005/v1/rerank"
QUERY = "储油库大气污染物排放标准的排放限值是多少？"
DOCS = [
    "表1 油气处理装置排放限值 污染物项目 排放浓度（g/m3） 处理效率（%） NMHC ≤25 ≥95",
    "本标准规定了储油库在储存、收发汽油过程中油气排放限值、控制技术要求和检测方法。",
    "今天天气不错，适合出去散步，公园里的花开得很好，孩子们在草地上玩耍。",
]

body = json.dumps({"model": "BGE-RERANK-V2-M3", "query": QUERY, "documents": DOCS}).encode()
req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
except Exception as e:
    print("调用失败:", e)
    raise SystemExit(1)

print("返回字段:", list(d.keys()))
res = d.get("results", [])
res.sort(key=lambda x: -x.get("relevance_score", 0))
print(f"查询：{QUERY}")
for r in res:
    i = r["index"]
    print(f"  score={r.get('relevance_score'):.6f}  [{i}] {DOCS[i][:46]}")

if not res:
    raise SystemExit("无结果")
top = res[0].get("relevance_score", 0)
last = res[-1].get("relevance_score", 0)
gap = top - last
print(f"\n最高与最低分差: {gap:.6f}")
if gap < 0.05:
    print("判定：❌ 重排服务缺少区分能力（分数几乎不随相关性变化）")
else:
    print("判定：✅ 重排有区分能力")
# 正确文档（下标 0）是否排到第一
order = [r["index"] for r in res]
print(f"排序: {order}  期望最优文档下标 0 排第一 → {'是' if order[0] == 0 else '否'}")
