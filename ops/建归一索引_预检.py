#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建归一索引前的两项预检（不对线上做任何修改）。

① **行序对齐**：vectors.npy 的第 i 行到底是不是 chunks.jsonl 的第 i 行？
   做法：抽 20 条**没有公式、归一后不变**的 chunk，重新嵌入一次，
   和磁盘上第 i 行向量比余弦 —— 接近 1.0 才说明"按行号替换向量"这条路成立。
   （这一步不能省：整个改造方案的安全前提就是它。）

② **吞吐**：43,144 条要重算多久？先跑 384 条测速，再外推。
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import requests

spec = importlib.util.spec_from_file_location(
    "tc", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)

IDX = Path("/data/fagui_rag/index")
EMB = "http://127.0.0.1:34004/v1/embeddings"
BATCH = 16


def embed(texts: list[str]) -> np.ndarray:
    r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=600)
    r.raise_for_status()
    vs = np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
    return vs / np.maximum(np.linalg.norm(vs, axis=1, keepdims=True), 1e-9)


print("加载索引…")
vecs = np.load(IDX / "vectors.npy", mmap_mode="r")
lines = []
for i, line in enumerate(open(IDX / "chunks.jsonl", encoding="utf-8")):
    c = json.loads(line)
    lines.append((c.get("text") or "", line))
print(f"vectors {vecs.shape}，chunks {len(lines)}")

# ---- ① 行序对齐：抽「归一后不变」的 chunk 重嵌入 ----
print("\n===== ① 行序对齐检查（20 条不变的 chunk 重嵌入）=====")
picks = []
step = len(lines) // 24
i = step
while len(picks) < 20 and i < len(lines):
    t = lines[i][0]
    if t and tc.clean_retrieved_text(t) == t and len(t) > 80:
        picks.append(i)
    i += step
texts = [lines[i][0] for i in picks]
new = embed(texts)
cos = []
for k, i in enumerate(picks):
    old = np.asarray(vecs[i], dtype=np.float32)
    old = old / max(float(np.linalg.norm(old)), 1e-9)
    cos.append(float(new[k] @ old))
cos = np.array(cos)
print(f"余弦：最小 {cos.min():.6f}，均值 {cos.mean():.6f}，最大 {cos.max():.6f}")
print(f"行号样本：{picks[:6]} …")
ok = cos.min() > 0.99
print("结论：", "✅ 行序对齐成立，可以按行号替换向量" if ok else
      "❌ 对不上！不能用『按行号替换』的方案，必须整库重算")

# ---- ② 吞吐 ----
print("\n===== ② 嵌入吞吐（测速 384 条）=====")
todo = [t for t, _ in lines if t and tc.clean_retrieved_text(t) != t][:384]
print(f"待测 {len(todo)} 条，批大小 {BATCH}")
t0 = time.time()
done = 0
for s in range(0, len(todo), BATCH):
    embed(todo[s:s + BATCH])
    done += len(todo[s:s + BATCH])
dt = time.time() - t0
rate = done / dt
print(f"用时 {dt:.1f}s，{rate:.1f} 条/秒 → 43,144 条预计 {43144/rate/60:.1f} 分钟")
print(f"（若整库 265,248 条重算：{265248/rate/60:.0f} 分钟 —— 这就是「只重算变了的」省下来的）")
