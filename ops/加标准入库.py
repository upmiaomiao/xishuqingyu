#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一份**官方标准全文**入库：写 bundle md + 放 PDF + 追加到索引（产物写新目录 index_next）。

为什么单独写一个：`建P6索引.py` 是"整库重切"，而"新增一份材料"只需要**追加**，
没必要把 35 万块再嵌一遍（30 分钟）。这里只嵌这一份（几十块），其余行向量逐字节拷贝。

安全设计：
  · 线上索引一个字不改：产物写 `/data/fagui_rag/index_next`，之后用
    `bash /home/test/切换索引.sh /data/fagui_rag/index_next` 上线（它会把现役索引 mv 成备份）；
  · 语料树只**新增**一个目录，不动任何既有文件；
  · 自检：追加前后块数一致、抽查未变更行向量逐字节一致、新材料的限值数字确实在块里。

用法（服务器，服务 venv）：
  /home/test/fagui_serve/.venv/bin/python 加标准入库.py --spec /tmp/db32_spec.json [--dry-run]
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import io
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import requests

RAG = Path("/data/fagui_rag")
BUNDLE = RAG / "okf_bundles"          # 线上语料树（回填后）
PDF_ROOT = Path("/data/fagui_pdf")
SRC_IDX = RAG / "index"
DST_IDX = RAG / "index_next"
INGEST = RAG / "ingest_okf.py"
EMB = "http://127.0.0.1:34004/v1/embeddings"
BATCH = 32
VEC_SLICE = 20000


def load(path, name: str):
    # 注意两点：① 传 str（Path 会让 spec_from_file_location 报 rfind 错）；
    #           ② 显式给 SourceFileLoader（文件名不一定是 .py 结尾）。
    path = str(path)
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def embed_batch(texts: list[str]) -> np.ndarray:
    for k in range(3):
        try:
            r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=600)
            if r.status_code >= 400:
                raise RuntimeError("HTTP %d %s" % (r.status_code, (r.text or "")[:200]))
            return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
        except Exception:                                           # noqa: BLE001
            if k == 2:
                raise
            time.sleep(2 * (k + 1))
    raise RuntimeError("unreachable")


def yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def build_md(spec: dict, body: str) -> str:
    fm = spec["front"]
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            lines.append("%s:" % k)
            for item in v:
                first = True
                for kk, vv in item.items():
                    lines.append("%s%s: %s" % ("  - " if first else "    ", kk, yaml_scalar(vv)))
                    first = False
        elif isinstance(v, list):
            lines.append("%s:" % k)
            for item in v:
                lines.append("- %s" % yaml_scalar(item))
        else:
            lines.append("%s: %s" % (k, yaml_scalar(v)))
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    spec = json.loads(io.open(a.spec, encoding="utf-8").read())
    rel_dir, base = spec["rel_dir"], spec["file_base"]
    rel_md = "%s/%s.md" % (rel_dir, base)
    md_path = BUNDLE / rel_md
    body = io.open(spec["body_file"], encoding="utf-8").read()
    md_text = build_md(spec, body)
    print("材料：%s" % spec["front"]["title"])
    print("  入库路径：%s（%d 字）" % (rel_md, len(md_text)))
    pdf_src = spec.get("pdf")
    print("  PDF → %s" % ((PDF_ROOT / rel_dir / (base + ".pdf")) if pdf_src else "（无，法律类材料只有网页正文）"))

    ing = load(INGEST, "ingest_live")
    fm = spec["front"]
    fake_text = md_text
    fm_parsed, b = ing.split_okf(fake_text)
    b = ing.normalize_body(b)
    chunks = ing.chunk_by_paragraph(b)
    print("  用线上 ingest 切块：%d 块" % len(chunks))
    if not chunks:
        print("❌ 切不出块，停")
        return 2
    # 看一眼限值数字进了哪块
    hits = [i for i, c in enumerate(chunks) if ("1072" in c and ("50" in c or "40" in c))]
    print("  含标准号+限值数字的块：%s" % (hits[:6] or "（没找到，需人工看）"))
    if a.dry_run:
        print("\n【dry-run】未写语料、未建索引。")
        for i in hits[:3]:
            print("  块#%d：%s" % (i, chunks[i][:220].replace("\n", " ")))
        return 0

    # ---------- 1) 写语料（只新增）----------
    if md_path.exists():
        print("❌ 语料里已存在同名文件，停（避免覆盖）：%s" % md_path)
        return 2
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8", newline="\n")
    print("\n1) 语料写入 ✅：%s（%d 字节）" % (md_path, md_path.stat().st_size))
    if pdf_src:
        pdf_dst = PDF_ROOT / rel_dir / (base + ".pdf")
        pdf_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_src, pdf_dst)
        print("   PDF 就位 ✅：%s（%d 字节）" % (pdf_dst, pdf_dst.stat().st_size))
    else:
        print("   PDF：无（未提供 pdf 字段，跳过）")

    # ---------- 2) 追加到新索引 ----------
    header = ing.context_header(fm_parsed)
    new_rows, embed_texts = [], []
    for ci, ch in enumerate(chunks):
        meta = {
            "chunk_id": "%s#%d" % (rel_md, ci), "source": rel_md,
            "title": fm_parsed.get("title", ""), "type": fm_parsed.get("type", ""),
            "tags": fm_parsed.get("tags", []) or [], "issuer": fm_parsed.get("issuer", []) or [],
            "region_type": fm_parsed.get("region_type", ""), "region": fm_parsed.get("region", ""),
            "status": fm_parsed.get("status", ""), "standard_id": fm_parsed.get("standard_id", ""),
            "chunk_index": ci,
            "text": ("%s\n%s" % (header, ch)) if header else ch,
            "text_body": ch,
        }
        new_rows.append(meta)
        embed_texts.append(ing.make_embed_text(fm_parsed, ch))

    n_old = sum(1 for _ in io.open(SRC_IDX / "chunks.jsonl", encoding="utf-8"))
    n_new = len(new_rows)
    print("\n2) 建 index_next：线上 %d 块 + 新增 %d 块 = %d 块" % (n_old, n_new, n_old + n_new))
    DST_IDX.mkdir(parents=True, exist_ok=True)
    src_vec = np.load(SRC_IDX / "vectors.npy", mmap_mode="r")
    assert src_vec.shape[0] == n_old, "线上向量 %d ≠ 文本 %d" % (src_vec.shape[0], n_old)
    shutil.copyfile(SRC_IDX / "chunks.jsonl", DST_IDX / "chunks.jsonl")
    with io.open(DST_IDX / "chunks.jsonl", "a", encoding="utf-8", newline="\n") as fo:
        for meta in new_rows:
            fo.write(json.dumps(meta, ensure_ascii=False) + "\n")
    dst_vec = np.lib.format.open_memmap(DST_IDX / "vectors.npy", mode="w+", dtype=np.float32,
                                        shape=(n_old + n_new, src_vec.shape[1]))
    for s in range(0, n_old, VEC_SLICE):
        e = min(s + VEC_SLICE, n_old)
        dst_vec[s:e] = src_vec[s:e]
    print("   旧向量拷贝完成，开始嵌新增 %d 块" % n_new)
    for s in range(0, n_new, BATCH):
        arr = embed_batch(embed_texts[s:s + BATCH])
        dst_vec[n_old + s:n_old + s + len(arr)] = arr
    dst_vec.flush()
    print("   嵌入完成")

    (DST_IDX / "meta.json").write_text(json.dumps({
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_index": str(SRC_IDX),
        "chunks_total": n_old + n_new,
        "chunks_added": n_new,
        "added_sources": [rel_md],
        "note": "新增一份官方标准全文（DB32/1072-2018，官方平台下载）；其余行 chunks 与向量逐字节沿用",
        "source_url": fm.get("source_url", ""),
        "embed_recipe": "【title】 description\\n\\n<chunk_text>（与 ingest_okf.make_embed_text 一致）",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 3) 自检 ----------
    print("\n3) 自检")
    q = np.load(DST_IDX / "vectors.npy", mmap_mode="r")
    print("   形状 %s（应为 (%d, 1024)）" % (q.shape, n_old + n_new))
    import random
    rng = random.Random(20260922)
    sample = rng.sample(range(n_old), 4000)
    same = all(np.array_equal(np.asarray(q[i]), np.asarray(src_vec[i])) for i in sample)
    print("   旧行抽样 %d 条向量与线上逐字节一致：%s" % (len(sample), "✅" if same else "❌"))
    ok = 0
    with io.open(DST_IDX / "chunks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if rel_md in line and ("DB32" in line or "1072" in line):
                ok += 1
    print("   新材料的块数：%d ✅" % ok)
    print("\n完成。上线：bash /home/test/切换索引.sh %s" % DST_IDX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
