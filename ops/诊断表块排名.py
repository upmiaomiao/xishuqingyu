#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：某问题下，标准表块在向量召回里吗？在重排里排第几？

用法（服务器上跑）：python 诊断表块排名.py "问题" 关键词
  关键词用于标记目标块（如 "测定均值"）
"""
import sys

sys.path.insert(0, "/data/fagui_rag")
import retriever as R  # noqa: E402

q = sys.argv[1]
KEY = sys.argv[2] if len(sys.argv) > 2 else "测定均值"

r = R.Retriever()
qv = r.embed(q)
print(f"问题：{q}\n标记关键词：{KEY}\n")

hits = r.recall(qv, top_k_vec=20)
print("=" * 104)
print(f"① 向量召回 {len(hits)} 条（顺序 = 向量相似度）")
for rank, (i, s) in enumerate(hits, 1):
    c = r.chunks[i]
    mark = "  ★目标块" if KEY in c["text"] else ""
    print(f"  {rank:>2}. sim={s:.3f} {str(c.get('standard_id'))[:20]:<22} "
          f"idx={str(c.get('chunk_index')):<4} {len(c['text']):>4}字 "
          f"{c['text'][:50].replace(chr(10), ' ')}{mark}")

cands = [(i, s, r.chunks[i]) for i, s in hits]
scored = r.rerank(q, cands, top_k=len(cands))
print("\n" + "=" * 104)
print(f"② 重排后 {len(scored)} 条（顺序 = rerank 分）")
for rank, c in enumerate(scored, 1):
    mark = "  ★目标块" if KEY in c["text"] else ""
    print(f"  {rank:>2}. rr={round(c.get('rerank_score') or 0, 3):<6} "
          f"{str(c.get('standard_id'))[:20]:<22} idx={str(c.get('chunk_index')):<4} "
          f"{len(c['text']):>4}字 {c['text'][:44].replace(chr(10), ' ')}{mark}")

n_auth = R.auth_need(q) if r.quota else 0
strict = r.quota and n_auth >= R.AUTH_MIN_STRICT
print("\n" + "=" * 104)
print(f"③ _select 结果（依据保底 {n_auth} 条，strict={strict}）")
for c in r._select(list(scored), 5, n_auth, strict=strict):
    mark = "  ★目标块" if KEY in c["text"] else ""
    print(f"  rr={round(c.get('rerank_score') or 0, 3):<6} "
          f"{str(c.get('standard_id'))[:20]:<22} idx={str(c.get('chunk_index')):<4} "
          f"{c['text'][:44].replace(chr(10), ' ')}{mark}")
