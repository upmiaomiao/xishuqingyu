#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语料级 LaTeX 归一：先证明"值得做"，再算清"要做多少"。

三问：
  ① 归一后有多少 chunk 真的变了？（决定要重算多少条向量）
  ② LaTeX 到底有没有拉低相似度？（含**对照组**：只改空白、不动公式，看 delta 是不是 0）
  ③ 归一能不能把"装着答案的块"往前提？（看目标块在池子里的名次变化）
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
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

EMB = "http://127.0.0.1:34004/v1/embeddings"


def embed_batch(texts: list[str]) -> np.ndarray:
    r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=300)
    r.raise_for_status()
    vs = np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
    n = np.linalg.norm(vs, axis=1, keepdims=True)
    return vs / np.maximum(n, 1e-9)


def normalize(t: str) -> str:
    """入库归一 = 与送进模型前同一套清洗（一个函数，不搞两套口径）。"""
    return tc.clean_retrieved_text(t)


print("===== ① 归一的影响面（全索引） =====")
changed = 0
total = 0
with_dollar = 0
maxlen_delta = 0
for line in open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8"):
    c = json.loads(line)
    t = c.get("text") or ""
    total += 1
    if "$" in t:
        with_dollar += 1
    if normalize(t) != t:
        changed += 1
print(f"chunk 总数 {total:,}，含 $ 的 {with_dollar:,}，归一后会变的 {changed:,}"
      f"（{changed/total*100:.1f}% → 需要重算这么多条向量）")

print("\n===== ② 相似度影响（含对照组） =====")
QUERIES = [
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
    "危险废物贮存设施的防渗与渗透系数要求",
    "生活垃圾填埋场的防渗层渗透系数限值",
    "二噁英的排放限值是多少",
    "渗滤液的pH值应控制在什么范围",
]
r = rv.Retriever()
for q in QUERIES:
    qv = r.embed(q)
    sims = r.vectors @ qv
    top = np.argsort(-sims)[:40]
    idxs = [int(i) for i in top if "$" in (r.chunks[i].get("text") or "")]
    if not idxs:
        print(f"\n【{q}】top-40 里没有含公式的块，跳过")
        continue
    orig = [r.chunks[i].get("text") or "" for i in idxs]
    norm = [normalize(t) for t in orig]
    ctrl = [re.sub(r"[ \t]{2,}", " ", t) for t in orig]      # 对照组：只动空白
    vo = embed_batch(orig)
    vn = embed_batch(norm)
    vc = embed_batch(ctrl)
    d_norm = (vn @ qv) - (vo @ qv)
    d_ctrl = (vc @ qv) - (vo @ qv)
    print(f"\n【{q}】top-40 里含公式的块 {len(idxs)} 条")
    print(f"   归一后相似度变化：均值 {d_norm.mean():+.4f}，"
          f"最大 {d_norm.max():+.4f}，最小 {d_norm.min():+.4f}，"
          f"提升的 {(d_norm > 1e-6).sum()}/{len(idxs)}")
    print(f"   对照组（只改空白）：均值 {d_ctrl.mean():+.6f}（应≈0，证明变化来自公式而不是改文本本身）")
    # 名次变化：把归一后的分数替换回去重排
    sims2 = sims.copy()
    for k, i in enumerate(idxs):
        sims2[i] = sims[i] + d_norm[k]
    for k, i in enumerate(idxs):
        before = int((sims > sims[i]).sum()) + 1
        after = int((sims2 > sims2[i]).sum()) + 1
        t = re.sub(r"\s+", " ", orig[k])
        flag = "↑" if after < before else ("↓" if after > before else "=")
        if abs(after - before) >= 1 and ("10" in t or "渗透" in t or "限值" in t):
            print(f"   {flag} 名次 {before} → {after}  {t[:76]}")

print("\n===== ③ 结论口径 =====")
print("如果②里『归一后相似度』普遍上升、而对照组≈0，说明 LaTeX 确实在拉低召回，")
print("重算这 %d 条向量是有依据的；否则就不该动索引。" % changed)
