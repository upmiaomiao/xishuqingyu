#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只查检索、不调模型：直接看 top-k 取到了哪些块。用于快速定位"内容在库里但捞不出来"。

用法（服务器上，用服务 venv 以便 import numpy / retriever）：
  RAG_INDEX_DIR=/data/fagui_rag/index_stage /home/test/fagui_serve/.venv/bin/python 查检索结果.py "问题"
  …并可选 --top-k-vec 60 --top-k 5
"""
import argparse
import os
import sys

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--top-k-vec", type=int, default=0)
    ap.add_argument("--top-k", type=int, default=5)
    a = ap.parse_args()

    r = Retriever()
    print(f"索引: {os.environ.get('RAG_INDEX_DIR', '/data/fagui_rag/index')}  "
          f"召回 {a.top_k_vec or 'env默认'} → 终选 {a.top_k}\n")
    hits = r.retrieve(a.query, a.top_k_vec, a.top_k)
    for i, h in enumerate(hits, 1):
        print(f"[{i}] rerank={h.get('rerank_score')}  {h.get('title','')[:44]}  "
              f"{h.get('standard_id','')}")
        print(f"    {h.get('source','')[:96]}#{h.get('chunk_index')}")
        print(f"    {' '.join((h.get('text') or '').split())[:300]}")
        print()
    # 向量召回的前几条（未经重排），便于判断是召回还是重排的问题
    qv = r.embed(a.query)
    print("---- 仅向量相似度 top 5（未经重排）----")
    for idx, sim in r.search(qv, top_k=5):
        c = r.chunks[idx]
        print(f"  {sim:.4f}  {c.get('title','')[:40]}  #{c.get('chunk_index')}")
        print(f"        {' '.join((c.get('text') or '').split())[:200]}")


if __name__ == "__main__":
    main()
