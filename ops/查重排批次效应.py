#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""决定性实验：重排分数是不是"批次相关"的？

现象：同一份济宁报告，旧版(候选20条)重排 0.9914，新版(候选60条)重排 0.3584。
两种可能：
  A) 只是取到了不同的块（同一份报告有上千块，块不同分数自然不同）
  B) 重排服务对同一批文档的分数依赖批内其它文档（softmax 归一化之类）——
     若是 B，跨批比较分数就不可靠，选取逻辑必须改成"批内排名"。

办法：把"旧版那 20 条"单独送重排，再把这 20 条混进 60 条里送一次，
      对同一块比较两次分数。同块同问，分数变了就是 B。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("rv2", "/data/fagui_rag/_staging/retriever_v2.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

r = m.Retriever()
print(f"语料：{ {k: len(v) for k, v in r.corpus_idx.items()} }", flush=True)

QUERIES = [
    "济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？",
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
    "二噁英的排放限值是多少？",
]


def rerank(query: str, cands: list) -> dict:
    """cands: [(idx, sim)] → {chunk_index: score}"""
    payload = [(i, s, r.chunks[i]) for i, s in cands]
    out = r.rerank(query, payload, top_k=len(payload))
    return {c["chunk_index"]: c["rerank_score"] for c in out}, {
    c["chunk_index"]: (c["source"], c["vec_sim"]) for c in out}


for q in QUERIES:
    print("\n" + "=" * 100)
    print("Q:", q)
    qv = r.embed(q)
    qq = qv / max(np.linalg.norm(qv), 1e-8)
    sims = r.vectors_norm @ qq

    # 旧版池：全局向量 top-20
    top20 = np.argpartition(-sims, 20)[:20]
    top20 = top20[np.argsort(-sims[top20])]
    pool_old = [(int(i), float(sims[i])) for i in top20]

    # 新版池
    pool_new = r.recall(qv, top_k_vec=20)
    print(f"  旧版池 {len(pool_old)} 条 / 新版池 {len(pool_new)} 条；"
          f"交集 {len({i for i, _ in pool_old} & {i for i, _ in pool_new})} 条")

    s_old, meta_old = rerank(q, pool_old)
    s_new, meta_new = rerank(q, pool_new)

    # 第三组：旧版 20 条 + 新版池里不在旧版池的 40 条 = 60 条
    extra = [(i, s) for i, s in pool_new if i not in {j for j, _ in pool_old}][:40]
    pool_mix = pool_old + extra
    s_mix, meta_mix = rerank(q, pool_mix)

    inter = sorted(set(s_old) & set(s_new), key=lambda k: -s_old[k])
    print(f"  两条相同的块 {len(inter)} 个，同一块在「20条批」与「60条批」的分数：")
    for k in inter[:6]:
        print(f"    chunk#{k:<5} 20条批={s_old[k]:.4f}   60条批={s_new.get(k, float('nan')):.4f}   "
              f"混合60批={s_mix.get(k, float('nan')):.4f}   {meta_old[k][0][:70]}")

    only_new = sorted(set(s_new) - set(s_old), key=lambda k: -s_new[k])[:5]
    print("  只在 60 条批里出现的块（来自依据语料配额）：")
    for k in only_new:
        print(f"    chunk#{k:<5} 60条批={s_new[k]:.4f}    {meta_new[k][0][:80]}")

    # 每组各自的前 5（批内排名），看是不是"池子一大，绝对分就整体走低"
    for tag, sc in (("20条批", s_old), ("60条批", s_new), ("混合60批", s_mix)):
        vals = sorted(sc.values(), reverse=True)[:5]
        arr = np.array(list(sc.values()))
        print(f"  {tag}: 前5={[round(v, 4) for v in vals]}  批内均值={arr.mean():.4f} 批内最大={arr.max():.4f}")
