#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：实际 import 的 retriever 是哪个文件，以及 diversify 在真实候选上是否生效。"""
import os
import sys

sys.path.insert(0, "/data/fagui_rag")
import retriever as R  # noqa: E402

print("module file   :", R.__file__)
print("PER_DOC_CAP   :", R.Retriever.PER_DOC_CAP)
print("has _dedup_key:", hasattr(R.Retriever, "_dedup_key"))
print("TOP_K_VEC     :", R.TOP_K_VEC)

r = R.Retriever()
q = "生活垃圾焚烧排污许可证申请与核发技术规范主要规定了哪些内容？"
qv = r.embed(q)
hits = r.search(qv, top_k=R.TOP_K_VEC)
cands = [(i, s, r.chunks[i]) for i, s in hits]
print(f"\n候选 {len(cands)} 个")
docs = [c[2]["text"] for c in cands]
import json
import urllib.request
body = json.dumps({"model": "BGE-RERANK-V2-M3", "query": q, "documents": docs}).encode()
req = urllib.request.Request(R.BGE_RERANK_URL, data=body,
                            headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    results = json.loads(resp.read().decode())["results"]
results.sort(key=lambda x: -x["relevance_score"])
print("重排返回条数:", len(results))
keys = [R.Retriever._dedup_key(cands[x["index"]][2]) for x in results[:8]]
print("前 8 条的 dedup key:", keys)
picked = R.Retriever.diversify(results, cands, 5, R.Retriever.PER_DOC_CAP)
print(f"\ndiversify 后 {len(picked)} 条:")
for x in picked:
    m = cands[x["index"]][2]
    print(f"  {x['relevance_score']:.4f}  {R.Retriever._dedup_key(m)}  #{m.get('chunk_index')}")
