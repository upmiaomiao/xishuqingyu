"""
灌库脚本：在 31.10 上跑
读 okf_bundles/**/*.md → 切块 → BGE-M3 embedding → 落盘

输出：
  <INDEX_DIR>/chunks.jsonl   每行一个 chunk 的元数据 + 文本
  <INDEX_DIR>/vectors.npy    N x 1024 float32
  <INDEX_DIR>/meta.json      总览

用法：
  python ingest_okf.py --dry-run      # 只切块并报告，不 embedding、不落盘（零成本预演）
  python ingest_okf.py --limit 50     # 只处理前 50 份（冒烟）
  python ingest_okf.py                # 全量重建

环境变量（都有默认值，便于在不碰生产的情况下预演）：
  BUNDLE_ROOT  默认 /data/fagui_rag/okf_bundles
  INDEX_DIR    默认 /data/fagui_rag/index
  EMBED_URL    默认 http://127.0.0.1:34004/v1/embeddings
               —— 原脚本写死 33004，该端口已无服务；这是 2026-09-16 修正后的端口。
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
import yaml

BUNDLE_ROOT = Path(os.environ.get("BUNDLE_ROOT", "/data/fagui_rag/okf_bundles"))
INDEX_DIR = Path(os.environ.get("INDEX_DIR", "/data/fagui_rag/index"))
INDEX_DIR.mkdir(parents=True, exist_ok=True)

BGE_M3_URL = os.environ.get("EMBED_URL", "http://127.0.0.1:34004/v1/embeddings")
BGE_M3_MODEL = "BGE-M3"

CHUNK_TARGET = 500      # 目标字符数
CHUNK_MAX = 900         # 单块上限（超过强制切）
BATCH_SIZE = 32         # BGE-M3 一次 embed 的条数


def probe_embed() -> int:
    """开工前先探一次嵌入服务：端口写错要立刻报清楚，别等几百批之后才炸。"""
    try:
        r = requests.post(BGE_M3_URL, json={"model": BGE_M3_MODEL, "input": ["探针"]}, timeout=20)
        r.raise_for_status()
        dim = len(r.json()["data"][0]["embedding"])
    except Exception as e:
        raise SystemExit(f"嵌入服务不可用：{BGE_M3_URL} → {type(e).__name__}: {e}")
    print(f"嵌入服务可用：{BGE_M3_URL}（维度 {dim}）")
    return dim


# ---------- 解析 OKF md ----------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_okf(text: str) -> tuple[dict, str]:
    """拆开 frontmatter 和正文"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    body = text[m.end():]
    return fm, body


# ---------- 切块 ----------

def normalize_body(body: str) -> str:
    """清干净一些 markdown 噪音：去掉图片行、连续空行压缩"""
    lines = []
    for ln in body.splitlines():
        if re.match(r"^\s*!\[.*?\]\(.*?\)\s*$", ln):
            continue  # 纯图片行
        lines.append(ln.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_table(p: str) -> bool:
    """markdown 表格块：首行为表头，第二行是 |---|---| 分隔行。"""
    lines = [ln for ln in p.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    head, sep = lines[0].strip(), lines[1].strip()
    return head.startswith("|") and set(sep) <= set("|-: ")


def _split_table(p: str, max_size: int) -> list[str]:
    """超长表格按行切成多块，每块重复表头 —— 单块太大时列关系会被截断。"""
    lines = p.splitlines()
    head = lines[:2]
    body = lines[2:]
    out, cur, cur_len = [], [], sum(len(x) + 1 for x in head)
    for ln in body:
        if cur and cur_len + len(ln) + 1 > max_size:
            out.append("\n".join(head + cur))
            cur, cur_len = [], sum(len(x) + 1 for x in head)
        cur.append(ln)
        cur_len += len(ln) + 1
    if cur:
        out.append("\n".join(head + cur))
    return out


def chunk_by_paragraph(text: str, target=CHUNK_TARGET, max_size=CHUNK_MAX) -> list[str]:
    """按段落累加切块；**表格单独成块**。

    为什么要单独成块：限值表（"表1 油气处理装置排放限值 / NMHC / ≤25 / ≥95"）如果和
    前后大段散文混在同一个 500~900 字的块里，向量相似度与重排分数都会被散文稀释，
    问"限值是多少"时根本排不上来 —— 实测就是这个问题。表格独立成块后，
    块里几乎全是"污染物项目 + 数值"，与限值类问题的匹配度显著提高。
    """
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    cur, cur_len = [], 0

    def flush():
        nonlocal cur, cur_len
        if cur:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [], 0

    for p in paras:
        if _is_table(p):
            flush()
            if len(p) <= max_size:
                chunks.append(p)
            else:
                chunks.extend(_split_table(p, max_size))
            continue
        if len(p) >= max_size:
            # 单段太大，flush 当前块，自己强制再切
            flush()
            # 强制按字数切
            for i in range(0, len(p), max_size):
                chunks.append(p[i : i + max_size])
            continue
        if cur_len + len(p) > target and cur:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [p], len(p)
        else:
            cur.append(p)
            cur_len += len(p) + 2
    flush()
    return [c for c in chunks if c.strip()]


# ---------- BGE-M3 embedding ----------

def embed_batch(texts: list[str], retries=3) -> np.ndarray:
    """批量调用 BGE-M3，返回 (N, 1024) float32"""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(
                BGE_M3_URL,
                json={"model": BGE_M3_MODEL, "input": texts},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()["data"]
            arr = np.array([d["embedding"] for d in data], dtype=np.float32)
            return arr
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


# ---------- 主流程 ----------

def make_embed_text(fm: dict, chunk_text: str) -> str:
    """给 BGE-M3 的输入文本：把 title + description 拼在 chunk 前面增强信号"""
    title = fm.get("title") or ""
    desc = fm.get("description") or ""
    prefix_parts = []
    if title:
        prefix_parts.append(f"【{title}】")
    if desc:
        prefix_parts.append(desc)
    prefix = " ".join(prefix_parts)
    if prefix:
        return f"{prefix}\n\n{chunk_text}"
    return chunk_text


def context_header(fm: dict) -> str:
    """给 chunk 正文加的来源抬头：标准名 + 标准号（+ 材料类型）。

    为什么必须加：正文块经常从"5.2.1"这种条款号开始，块里根本没有标准名。
    只把标题拼进 embedding 输入是不够的 —— **重排器与给模型的上下文用的都是
    chunks.jsonl 里的 text**，看不到标题就会出现"问一般工业固废，却把
    GB 18599 里只含'5.2 I类场技术要求'标题的块排到前面，而含 1.0×10-5 数值的块
    根本进不了 top-k"。抬头写进 text 后，向量检索与重排都能利用标准名。
    """
    title = (fm.get("title") or "").strip()
    sid = (fm.get("standard_id") or "").strip()
    doc_type = (fm.get("type") or "").strip()
    parts = []
    if title:
        parts.append(f"【{title}】")
    if sid:
        parts.append(sid)
    if doc_type and doc_type != "standard":
        parts.append(doc_type)
    return " ".join(parts)


def main():
    dry_run = "--dry-run" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    print(f"扫描 {BUNDLE_ROOT}")
    all_md = sorted(BUNDLE_ROOT.rglob("*.md"))
    if limit:
        all_md = all_md[:limit]
    print(f"找到 {len(all_md)} 份 md" + (f"（--limit {limit}）" if limit else ""))
    print(f"输出目录 {INDEX_DIR}" + ("　【dry-run：不 embedding、不落盘】" if dry_run else ""))
    if not dry_run:
        probe_embed()          # 端口/服务不对时立刻失败，别等几百批

    # 阶段 1: 切块（不调 embed）
    all_chunks = []  # 每个元素：(chunk_text_for_embed, metadata_dict)
    file_skip = 0
    for i, md in enumerate(all_md):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  read err {md}: {e}")
            file_skip += 1
            continue
        fm, body = split_okf(text)
        body = normalize_body(body)
        if not body:
            continue
        chunks = chunk_by_paragraph(body)
        header = context_header(fm)
        for ci, ch in enumerate(chunks):
            meta = {
                "chunk_id": f"{md.relative_to(BUNDLE_ROOT).as_posix()}#{ci}",
                "source": md.relative_to(BUNDLE_ROOT).as_posix(),
                "title": fm.get("title", ""),
                "type": fm.get("type", ""),
                "tags": fm.get("tags", []) or [],
                "issuer": fm.get("issuer", []) or [],
                "region_type": fm.get("region_type", ""),
                "region": fm.get("region", ""),
                "status": fm.get("status", ""),
                "standard_id": fm.get("standard_id", ""),
                "chunk_index": ci,
                # text 带来源抬头（重排与模型上下文都用它）；text_body 保留原正文便于排查
                "text": f"{header}\n{ch}" if header else ch,
                "text_body": ch,
            }
            all_chunks.append((make_embed_text(fm, ch), meta))
        if (i + 1) % 500 == 0:
            print(f"  切块进度 {i+1}/{len(all_md)} | 累计 chunks: {len(all_chunks)}")

    print(f"\n切块完成：{len(all_chunks)} 个 chunks（跳过 {file_skip} 份文件）")

    # 按来源语料统计一下，便于确认新增/删除生效
    from collections import Counter
    corpus = Counter(m["source"].split("/")[0] for _, m in all_chunks)
    print("  按语料 chunk 数：", dict(corpus.most_common()))

    if dry_run:
        print("\n【dry-run 结束】未调用 embedding、未落盘。")
        return

    # 阶段 2: 批量 embedding
    print(f"\n开始 embedding（batch={BATCH_SIZE}, BGE-M3 @ {BGE_M3_URL}）")
    t0 = time.time()
    n = len(all_chunks)
    vectors = np.zeros((n, 1024), dtype=np.float32)

    for start in range(0, n, BATCH_SIZE):
        batch = all_chunks[start : start + BATCH_SIZE]
        texts = [b[0] for b in batch]
        try:
            arr = embed_batch(texts)
        except Exception as e:
            print(f"  ❌ batch {start} embed 失败: {e}")
            raise
        vectors[start : start + len(batch)] = arr
        if (start // BATCH_SIZE) % 20 == 0:
            elapsed = time.time() - t0
            rate = (start + len(batch)) / elapsed if elapsed > 0 else 0
            eta = (n - start - len(batch)) / rate if rate > 0 else 0
            print(f"  [{start+len(batch):>6}/{n}] {rate:.1f} chunk/s · ETA {eta/60:.1f} min")

    elapsed = time.time() - t0
    print(f"\nembedding 完成：{elapsed/60:.1f} 分钟（{n/elapsed:.1f} chunk/s）")

    # 阶段 3: 落盘
    print(f"\n落盘到 {INDEX_DIR}")
    np.save(INDEX_DIR / "vectors.npy", vectors)

    with open(INDEX_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for _, meta in all_chunks:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    meta_summary = {
        "total_chunks": n,
        "total_files": len(all_md),
        "dim": 1024,
        "embed_model": "BGE-M3",
        "bundle_root": str(BUNDLE_ROOT),
        "chunk_target": CHUNK_TARGET,
        "chunk_max": CHUNK_MAX,
        "elapsed_seconds": elapsed,
        "generated_at": int(time.time()),
    }
    (INDEX_DIR / "meta.json").write_text(
        json.dumps(meta_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 文件大小报告
    vec_size = (INDEX_DIR / "vectors.npy").stat().st_size / 1024 / 1024
    chunks_size = (INDEX_DIR / "chunks.jsonl").stat().st_size / 1024 / 1024
    print(f"\n✓ vectors.npy = {vec_size:.1f} MB")
    print(f"✓ chunks.jsonl = {chunks_size:.1f} MB")
    print(f"✓ 总 chunks: {n}")


if __name__ == "__main__":
    main()
