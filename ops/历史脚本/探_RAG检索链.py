#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 .10 上探清 RAG 检索链到底断在哪一环。

问题背景：站点对任何专业问题返回 502「检索服务异常：127.0.0.1:34004 连接被拒」。
要区分两种情况（结论完全不同）：
  A. 服务只是挪了端口 —— 那改一行 URL 就好；
  B. 换了模型、索引与新模型不兼容 —— 那必须重建索引，改 URL 只会得到垃圾检索。
"""
import json
import socket
from pathlib import Path

import numpy as np
import requests

print("=" * 70)
print("[1] 索引本身")
idx = Path("/data/fagui_rag/index")
print("  meta.json:", (idx / "meta.json").read_text(encoding="utf-8").strip()[:400])
v = np.load(idx / "vectors.npy", mmap_mode="r")
print("  vectors.npy 形状: %s（即 %d 条 × %d 维）" % (v.shape, v.shape[0], v.shape[1]))
n = sum(1 for _ in open(idx / "chunks.jsonl", encoding="utf-8"))
print("  chunks.jsonl 行数: %d" % n)
print("  条数与向量数一致:", n == v.shape[0])

print("\n" + "=" * 70)
print("[2] 端口连通性")
for port in (34004, 34005, 8001, 8002, 8000):
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(("127.0.0.1", port))
        print("  127.0.0.1:%-6d 可连接" % port)
    except Exception as e:
        print("  127.0.0.1:%-6d 不可连接（%s）" % (port, type(e).__name__))
    finally:
        s.close()

print("\n" + "=" * 70)
print("[3] 现存的嵌入服务（8001）与索引是否同一模型空间")
try:
    r = requests.post("http://127.0.0.1:8001/v1/embeddings",
                      json={"model": "bge-zh-emb", "input": ["危险废物贮存要求"]}, timeout=60)
    r.raise_for_status()
    emb = r.json()["data"][0]["embedding"]
    print("  8001 返回维度: %d" % len(emb))
    print("  索引维度    : %d" % v.shape[1])
    print("  ★ 维度是否一致:", len(emb) == v.shape[1])
    if len(emb) != v.shape[1]:
        print("  → 结论：换模型了，索引必须重建，光改 URL 不行")
    else:
        print("  → 维度相同，但仍需验向量空间（同一句在两模型下的相似度排序是否一致）")
except Exception as e:
    print("  8001 调用失败：%s: %s" % (type(e).__name__, e))

print("\n" + "=" * 70)
print("[4] 直接调 retriever.retrieve()，看真实报错")
import sys
sys.path.insert(0, "/data/fagui_rag")
try:
    from retriever import Retriever
    rt = Retriever()
    try:
        hits = rt.retrieve("危险废物贮存污染控制标准对贮存设施的要求", 20, 3)
        print("  检索成功，命中 %d 条" % len(hits))
        for i, h in enumerate(hits, 1):
            print("    [%d] %s | rerank=%s" % (i, str(h.get("title"))[:60], h.get("rerank_score")))
    except Exception as e:
        print("  ★ 检索失败：%s: %s" % (type(e).__name__, e))
except Exception as e:
    print("  导入/加载失败：%s: %s" % (type(e).__name__, e))
