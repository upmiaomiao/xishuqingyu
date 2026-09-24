#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只查一件事：归一之后，"装着 1.0×10⁻⁵ 的那个块"为什么掉出了引用位？

对同一个问题，在 v1（LaTeX 原文）与 v2（归一文本）两个索引上，
把候选池里的依据块按"原始重排分 + 数值加权"完整列出来，一眼看出差在哪。
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location("rv", "/data/fagui_rag/retriever.py")
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)

Q = "一般工业固体废物贮存场 I 类场的防渗要求是什么？"

for tag, idx in (("v1 LaTeX 原文", "/data/fagui_rag/index"),
                 ("v2 归一文本", "/data/fagui_rag/index_v2")):
    r = rv.Retriever(index_dir=Path(idx))
    qv = r.embed(Q)
    hits = r.recall(qv, top_k_vec=20)
    cands = [(i, s, r.chunks[i]) for i, s in hits]
    scored = r.rerank(Q, cands, top_k=max(len(cands), 5))
    n_auth = rv.auth_need(Q)
    strict = n_auth >= rv.AUTH_MIN_STRICT
    print(f"\n{'='*100}\n【{tag}】依据保底 {n_auth} 条，strict={strict}，候选 {len(cands)}")
    rows = []
    for c in scored:
        text = c.get("text") or ""
        is_auth = rv.is_authority(c)
        num = bool(rv.RE_NUMERIC.search(text)) if is_auth else False
        b = rv.NUM_BONUS if (strict and is_auth and num) else 0.0
        rows.append((c.get("rerank_score", 0) + b, c.get("rerank_score", 0), b, num, c))
    rows.sort(key=lambda x: -x[0])
    for eff, raw, b, num, c in rows[:9]:
        src = (c.get("source") or "").split("/")[-1][:34]
        mark = "★数值" if num else "     "
        print(f"  有效 {eff:.4f} = 原始 {raw:.4f} + 加权 {b:.2f}  {mark} {src}#{c.get('chunk_index')}")
        if num:
            t = re.sub(r"\s+", " ", c.get("text") or "")
            print(f"        命中片段：{t[:88]}")
    final = r._select(scored, 5, n_auth, strict=strict)
    print("  最终引用：", [f"{(c.get('source') or '').split('/')[-1][:22]}#{c.get('chunk_index')}"
                          f"({round(c.get('rerank_score') or 0, 3)})" for c in final])
    # 目标块 v1/v2 的原文对照
    tgt = [c for c in scored if (c.get("source") or "").endswith("GB 18599－2020.md")
           and c.get("chunk_index") == 13]
    if tgt:
        t = re.sub(r"\s+", " ", tgt[0].get("text") or "")
        print(f"  #13 原始重排 {tgt[0].get('rerank_score'):.4f}；文本开头：{t[:70]}")
    else:
        print("  #13 不在候选池里")
