#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专项验证：邻块扩展有没有把「I 类场防渗数值块」带进候选池并选中。

顺便验一个索引前提：同一份文档的块在 chunks.jsonl 里是不是**连续排列**、
chunk_index 是不是**递增 1**。邻块扩展（idx±1）全靠这个前提。
"""
from __future__ import annotations

import importlib.util
import re

spec = importlib.util.spec_from_file_location("rv2", "/data/fagui_rag/_staging/retriever_v2.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

r = m.Retriever()

# ---- 前提验证：同文档块是否连续、chunk_index 是否递增 ----
bad = 0
seq_ok = 0
for i in range(len(r.chunks) - 1):
    a, b = r.chunks[i], r.chunks[i + 1]
    if a.get("source") == b.get("source"):
        if (b.get("chunk_index") or 0) == (a.get("chunk_index") or 0) + 1:
            seq_ok += 1
        else:
            bad += 1
            if bad <= 3:
                print(f"  ⚠ chunk_index 不连续：{a.get('source')} "
                      f"{a.get('chunk_index')} → {b.get('chunk_index')}")
print(f"邻块前提：同文档相邻行且 chunk_index+1 的有 {seq_ok} 对，异常 {bad} 对")

NUMPAT = re.compile(r"1\.0\{\\times\}10\^\{-5\}|1\.0\s*×\s*10\s*[-−]\s*5")

for q, needle in [
    ("一般工业固体废物贮存场 I 类场的防渗要求是什么？", "GB 18599"),
    ("二噁英的排放限值是多少？", "18484"),
]:
    print("\n" + "=" * 100)
    print("Q:", q)
    qv = r.embed(q)
    hits = r.recall(qv, top_k_vec=20)
    pool = [(i, s, r.chunks[i]) for i, s in hits]
    rel = [x for x in pool if needle in (x[2].get("source") or "")]
    print(f"  候选池 {len(pool)} 条，其中含「{needle}」的 {len(rel)} 条")
    scored = r.rerank(q, pool, top_k=len(pool))
    scored.sort(key=lambda c: -(c.get("rerank_score") or 0))
    for c in scored:
        if needle not in (c.get("source") or ""):
            continue
        t = re.sub(r"\s+", " ", c.get("text") or "")
        mark = "★含数值" if NUMPAT.search(c.get("text") or "") else ""
        print(f"    chunk#{c.get('chunk_index'):<5} rerank={c.get('rerank_score'):.4f} "
              f"vec={c.get('vec_sim'):.4f} {mark}  {t[:110]}")
    got = r.retrieve(q, 20, 5)
    print("  最终引用：")
    for i, c in enumerate(got, 1):
        t = re.sub(r"\s+", " ", c.get("text") or "")
        mark = "★含数值" if NUMPAT.search(c.get("text") or "") else ""
        print(f"    [{i}] {'依据' if m.is_authority(c) else '案例'} "
              f"rerank={c.get('rerank_score'):.4f} {mark} "
              f"{c.get('source','')[:56]}#{c.get('chunk_index')}")
        if mark:
            print(f"         {t[:200]}")
