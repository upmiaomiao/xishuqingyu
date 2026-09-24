#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现"线上向量是怎么算出来的"。

预检发现：直接嵌入块正文，与磁盘向量余弦只有 0.86 —— 说明配方不同。
读入库脚本（ingest_okf.py）看到它是嵌入 `【title】 description\\n\\n 正文`。
本脚本用几种候选拼法各试一遍，找出哪个能把余弦打到 ≈1.0。
只有找到它，"只重算变了的块、其余沿用原向量"这条安全路才成立。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import requests
import yaml

importlib.util.spec_from_file_location  # noqa: B018  (保持 import 列表整齐)
spec = importlib.util.spec_from_file_location(
    "tc", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)

IDX = Path("/data/fagui_rag/index")
BUNDLE = Path("/data/fagui_rag/okf_bundles")
EMB = "http://127.0.0.1:34004/v1/embeddings"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def embed(texts: list[str]) -> np.ndarray:
    r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=600)
    r.raise_for_status()
    return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)


def unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-9)


print("抽 16 条「归一后不变」的块（保证块正文与入库时一致）…")
vecs = np.load(IDX / "vectors.npy", mmap_mode="r")
picks = []
fm_cache: dict[str, dict] = {}
with open(IDX / "chunks.jsonl", encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        if i % 16000 != 0:
            continue
        c = json.loads(line)
        t = c.get("text") or ""
        if len(t) > 120 and tc.clean_retrieved_text(t) == t:
            picks.append((i, c))
print(f"样本 {len(picks)} 条")

for i, c in picks:
    src = c["source"]
    if src not in fm_cache:
        raw = (BUNDLE / src).read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.match(raw)
        fm_cache[src] = (yaml.safe_load(m.group(1)) or {}) if m else {}

variants = {
    "A 只有正文": lambda fm, t: t,
    "B 【title】+正文": lambda fm, t: f"【{fm.get('title','')}】\n\n{t}",
    "C 【title】 description+正文": lambda fm, t: (
        f"【{fm.get('title','')}】 {fm.get('description','')}\n\n{t}"
        if fm.get("description") else f"【{fm.get('title','')}】\n\n{t}"),
    "D title 不加书名号+正文": lambda fm, t: f"{fm.get('title','')}\n\n{t}",
}

print("\n各候选拼法 vs 磁盘向量的余弦（找 ≈1.0 的那个）")
print("=" * 78)
for name, fn in variants.items():
    texts = [fn(fm_cache[c["source"]], c["text"]) for _, c in picks]
    got = embed(texts)
    cos = np.array([float(unit(got[k]) @ unit(np.asarray(vecs[i], dtype=np.float32)))
                    for k, (i, _) in enumerate(picks)])
    print(f"{name:34} 最小 {cos.min():.6f}  均值 {cos.mean():.6f}  最大 {cos.max():.6f}")

print("\n参考：入库脚本的原文拼法")
print('  make_embed_text → "【title】 description" + "\\n\\n" + chunk_text')
c0 = picks[0][1]
fm0 = fm_cache[c0["source"]]
print(f"  样本块 source = {c0['source'][:70]}")
print(f"  front matter 的 title = {fm0.get('title','')!r}")
print(f"  front matter 有 description 吗 = {bool(fm0.get('description'))}")
