#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归一化对**重排**的影响（这才是决定引用名次的那一路）。

重排器（BGE-RERANK-V2-M3）读的候选文本来自 chunks.jsonl，同样是 LaTeX 原文：
`$1.0{\times}10^{-5}\,\mathrm{cm/s}$` 这种串，交叉编码器未必读得出"数值"。
本脚本对同一批候选分别用「原文」和「归一文本」打重排分，比差值。
对照组：只把连续空格压成一个（文本几乎没变），delta 应≈0。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys

import requests

for p in ("/data/fagui_rag", "/home/test/xishu_qingyu_serve"):
    sys.path.insert(0, p)

spec = importlib.util.spec_from_file_location("rv", "/data/fagui_rag/retriever.py")
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)
spec2 = importlib.util.spec_from_file_location(
    "tc", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")
tc = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(tc)

RERANK = "http://127.0.0.1:34005/v1/rerank"


def rerank(query: str, docs: list[str]) -> list[float]:
    r = requests.post(RERANK, json={"model": "BGE-RERANK-V2-M3", "query": query,
                                    "documents": docs}, timeout=600)
    r.raise_for_status()
    out = sorted(r.json()["results"], key=lambda d: d["index"])
    return [d["relevance_score"] for d in out]


def norm(t: str) -> str:
    return tc.clean_retrieved_text(t)


QUERIES = [
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
    "生活垃圾填埋场的防渗层渗透系数限值",
    "二噁英的排放限值是多少",
    "渗滤液的pH值应控制在什么范围",
    "危险废物贮存设施的选址要求",
    "排污许可证的有效期是多久",
]

r = rv.Retriever()
print("同一批候选：原文 vs 归一文本 的重排分对比")
print("=" * 92)
grand = []
for q in QUERIES:
    qv = r.embed(q)
    idxs = r.recall(qv, top_k_vec=20)
    docs = [r.chunks[i].get("text") or "" for i, _ in idxs]
    n_docs = [norm(d) for d in docs]
    c_docs = [re.sub(r"[ \t]{2,}", " ", d) for d in docs]        # 对照组
    so = rerank(q, docs)
    sn = rerank(q, n_docs)
    sc = rerank(q, c_docs)
    deltas = [b - a for a, b in zip(so, sn)]
    ctrl = [b - a for a, b in zip(so, sc)]
    grand += deltas
    print(f"\n【{q}】候选 {len(docs)} 条")
    print(f"   重排分变化：均值 {sum(deltas)/len(deltas):+.4f}，最大 {max(deltas):+.4f}，"
          f"最小 {min(deltas):+.4f}，上升的 {sum(1 for d in deltas if d > 1e-4)}/{len(deltas)}")
    print(f"   对照组（压空格）：均值 {sum(ctrl)/len(ctrl):+.6f}（应≈0）")
    # 前 5 名有没有换人
    top_o = sorted(range(len(docs)), key=lambda k: -so[k])[:5]
    top_n = sorted(range(len(docs)), key=lambda k: -sn[k])[:5]
    same = len(set(top_o) & set(top_n))
    print(f"   重排 top-5 重合 {same}/5")
    for k in top_n[:3]:
        if k not in top_o:
            t = re.sub(r"\s+", " ", n_docs[k])
            print(f"     ↑ 新进前五：{t[:78]}")
    for k in top_o[:3]:
        if k not in top_n:
            t = re.sub(r"\s+", " ", n_docs[k])
            print(f"     ↓ 掉出前五：{t[:78]}")

print("\n" + "=" * 92)
n = len(grand)
print(f"总体：{n} 条候选，重排分变化 均值 {sum(grand)/n:+.4f}，"
      f"上升 {sum(1 for d in grand if d > 1e-4)}，下降 {sum(1 for d in grand if d < -1e-4)}，"
      f"基本不变 {sum(1 for d in grand if abs(d) <= 1e-4)}")
