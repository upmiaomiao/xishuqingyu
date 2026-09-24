#!/usr/bin/env python3
# 验证 rerank 是否真的回到检索链里：比对答复来源里有没有 rerank_score。
import json
import urllib.error
import urllib.request

SITE = "http://10.201.31.10:8011"
Q = "固体废物污染环境防治法对危险废物贮存有什么要求？"


def post(path, payload, timeout=240):
    req = urllib.request.Request(
        SITE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


st, body = post("/hybrid_search", {"query": Q})
print("HTTP", st, "route =", body.get("route") if isinstance(body, dict) else "?")
srcs = (body.get("sources") or []) if isinstance(body, dict) else []
print("来源数 =", len(srcs))

if srcs:
    print("\n第一条来源的完整字段：")
    for k, v in srcs[0].items():
        s = str(v)
        print(f"  {k} = {s[:90]}{'...' if len(s) > 90 else ''}")

    have = sum(1 for s in srcs if s.get("rerank_score") is not None)
    print(f"\n带 rerank_score 的来源：{have}/{len(srcs)}")
    if have:
        print("rerank_score 取值：", [round(s["rerank_score"], 3) if s.get("rerank_score") is not None else None for s in srcs])
        print("→ rerank 已回到检索链 ✓")
    else:
        print("→ 仍然没有 rerank_score，rerank 未生效 ✗")
