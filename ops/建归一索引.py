#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建"归一索引" index_v2（不动线上 index）。

做什么：
  1. chunks.jsonl：把每块正文过一遍入库归一（与送进模型前同一套清洗：LaTeX → 可读文本）。
     **未变的行逐字节原样拷贝**，变了的行才重写（只有 text 字段变）。
  2. vectors.npy：先整份拷贝线上向量，再把"变了的行"用**与入库完全相同的配方**重算后替换：
        embed 输入 = "【title】 description" + "\\n\\n" + 块正文
     （配方已实测复现：余弦 0.999997~1.000000，见 建归一索引_复现配方.py）
  3. meta.json：记录源索引、变更条数、配方、指纹 —— 将来能说清这份索引是怎么来的。

为什么敢只重算一部分：未变的行文本一字未改，配方又已验证可复现，
所以那些行沿用原向量在数学上就是同一件事；只有变了的行必须重算。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
import yaml

SRC_IDX = Path("/data/fagui_rag/index")
DST_IDX = Path("/data/fagui_rag/index_v2")
BUNDLE = Path("/data/fagui_rag/okf_bundles")
EMB = "http://127.0.0.1:34004/v1/embeddings"
BATCH = 32
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

spec = importlib.util.spec_from_file_location(
    "tc", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)


def embed(texts: list[str], retries: int = 3) -> np.ndarray:
    last = None
    for k in range(retries):
        try:
            r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=300)
            r.raise_for_status()
            return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
        except Exception as e:                     # 网络抖动就重试，别整批报废
            last = e
            time.sleep(2 * (k + 1))
    raise last


def main() -> None:
    DST_IDX.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---------- 阶段 1：归一文本 ----------
    print("阶段 1/3：归一 chunks.jsonl（未变的行原样拷贝）")
    changed: list[tuple[int, dict]] = []          # (行号, 元数据)
    total = 0
    n_changed = 0
    with open(SRC_IDX / "chunks.jsonl", encoding="utf-8") as fi, \
            open(DST_IDX / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as fo:
        for i, line in enumerate(fi):
            total += 1
            obj = json.loads(line)
            old = obj.get("text") or ""
            new = tc.clean_retrieved_text(old)
            if new == old:
                fo.write(line)                    # 逐字节原样，不重新序列化
                continue
            obj["text"] = new
            fo.write(json.dumps(obj, ensure_ascii=False) + "\n")
            changed.append((i, {"source": obj.get("source", ""),
                                "chunk_index": obj.get("chunk_index"),
                                "title": obj.get("title", ""),
                                "text": new}))
            n_changed += 1
            if n_changed % 10000 == 0:
                print(f"   已处理 {total:,} 行，其中改过 {n_changed:,}")
    print(f"   chunks.jsonl 完成：{total:,} 行，改过 {n_changed:,} 行（{n_changed/total*100:.1f}%）"
          f"，用时 {time.time()-t0:.0f}s")

    # ---------- 阶段 2：拷贝向量 + 重算变更行 ----------
    print("\n阶段 2/3：拷向量 → 重算变更行")
    vecs = np.load(SRC_IDX / "vectors.npy", mmap_mode="r")
    assert vecs.shape[0] == total, f"行数对不上：向量 {vecs.shape[0]} vs 文本 {total}"
    np.save(DST_IDX / "vectors.npy", np.asarray(vecs))       # 先整份拷贝
    del vecs
    out = np.load(DST_IDX / "vectors.npy", mmap_mode="r+")

    fm_cache: dict[str, dict] = {}
    no_fm = 0

    def embed_text(meta: dict) -> str:
        nonlocal no_fm
        src = meta["source"]
        if src not in fm_cache:
            p = BUNDLE / src
            if p.is_file():
                m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8", errors="replace"))
                fm_cache[src] = (yaml.safe_load(m.group(1)) or {}) if m else {}
            else:
                fm_cache[src] = {}
        fm = fm_cache[src]
        if not fm:
            no_fm += 1
            fm = {"title": meta.get("title", "")}    # 兜底：用 chunks.jsonl 里的标题
        parts = []
        if fm.get("title"):
            parts.append(f"【{fm['title']}】")
        if fm.get("description"):
            parts.append(str(fm["description"]))
        prefix = " ".join(parts)
        return f"{prefix}\n\n{meta['text']}" if prefix else meta["text"]

    t1 = time.time()
    done = 0
    for s in range(0, len(changed), BATCH):
        batch = changed[s:s + BATCH]
        arr = embed([embed_text(m) for _, m in batch])
        for k, (row, _) in enumerate(batch):
            out[row] = arr[k]
        done += len(batch)
        if done % 3200 == 0 or done == len(changed):
            el = time.time() - t1
            rate = done / el if el else 0
            eta = (len(changed) - done) / rate if rate else 0
            print(f"   [{done:>6}/{len(changed)}] {rate:.1f} 条/s · ETA {eta/60:.1f} min")
    out.flush()
    print(f"   重算完成，用时 {(time.time()-t1)/60:.1f} 分钟；没读到 front matter 的 {no_fm} 条（应为 0）")

    # ---------- 阶段 3：自检 ----------
    print("\n阶段 3/3：自检")
    v1 = np.load(SRC_IDX / "vectors.npy", mmap_mode="r")
    v2 = np.load(DST_IDX / "vectors.npy", mmap_mode="r")
    changed_rows = {row for row, _ in changed}
    rng = np.random.default_rng(0)
    sample = [i for i in rng.choice(total, size=4000, replace=False) if i not in changed_rows]
    same = all(np.array_equal(np.asarray(v1[i]), np.asarray(v2[i])) for i in sample)
    print(f"   未变更行抽样 {len(sample)} 条与线上逐字节一致：{'✅' if same else '❌'}")
    diff_rows = [i for i in rng.choice(sorted(changed_rows), size=200, replace=False)]
    differ = sum(1 for i in diff_rows if not np.array_equal(np.asarray(v1[i]), np.asarray(v2[i])))
    print(f"   变更行抽样 200 条中确有新向量：{differ}/200 "
          f"{'✅' if differ >= 195 else '❌'}")

    # 目标块：GB 18599-2020 的 5.2.1 应该已经带上数值
    hits = []
    with open(DST_IDX / "chunks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if "10⁻⁵" in line and "GB 18599" in line:
                hits.append(json.loads(line))
    print(f"   归一后带 10⁻⁵ 的 GB 18599 块：{len(hits)} 条")
    for h in hits[:2]:
        print(f"      chunk#{h.get('chunk_index')}：{h['text'][:110]}")

    (DST_IDX / "meta.json").write_text(json.dumps({
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_index": str(SRC_IDX),
        "chunks_total": total,
        "chunks_changed": n_changed,
        "embed_recipe": "【title】 description\\n\\n<chunk_text>（与 ingest_okf.py 一致，已实测复现）",
        "normalizer": "xishu_pipeline/textclean.py::clean_retrieved_text",
        "textclean_md5": hashlib.md5(Path(tc.__file__).read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成，总用时 {(time.time()-t0)/60:.1f} 分钟。索引目录：{DST_IDX}")


if __name__ == "__main__":
    sys.exit(main())
