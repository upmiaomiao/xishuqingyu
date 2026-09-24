#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建 P6 索引：用 **P6 版 ingest** 重切"文本变了的那批文档"，其余行逐字节沿用线上向量。

为什么要单独写一个（而不是用现成的 建归一索引.py）：
  建归一索引.py 是"文本归一"版 —— 它在**行内**改 text 再重嵌，行数不变、行序不变。
  P6 是**重新切块** —— 受影响文档的块数会变（实测 219,945 行 → 263,754 块，净增 43,809），
  所以必须按"文档"为单位替换行块，不能用行内替换。

安全性（每一步都能回退）：
  · 只读线上 `/data/fagui_rag/index` 与语料树 `/data/fagui_rag/okf_bundles_p6`；
  · 全部产物写**新目录** `/data/fagui_rag/index_p6`，线上索引一个字都不动；
  · 未受影响的行：chunks.jsonl **逐字节原样拷贝**、向量**整段切片拷贝**（不重算）；
  · 自检：未变更行抽样向量与线上逐字节一致 + 关键探针（储油库 ≤25/≥95）。

用法（服务器）：
  /home/test/fagui_serve/.venv/bin/python 建P6索引.py --dry-run    # 只数块、不写盘、不嵌入
  /home/test/fagui_serve/.venv/bin/python 建P6索引.py              # 真正建（写 index_p6）
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests

SRC_IDX = Path("/data/fagui_rag/index")
DST_IDX = Path("/data/fagui_rag/index_p6")
P6_TREE = Path("/data/fagui_rag/okf_bundles_p6")
LIVE_INGEST = "/data/fagui_rag/ingest_okf.py"
P6_INGEST = "/data/fagui_rag/ingest_okf.py.p6_20260916"
EMB = "http://127.0.0.1:34004/v1/embeddings"
BATCH = 32
VEC_SLICE = 20000          # 向量拷贝分片，避免一次性读 900 MB


def load(path: str, name: str):
    # 注意：文件后缀是 .p6_20260916（不是 .py），spec_from_file_location 推断不出 loader，
    # 必须显式给 SourceFileLoader。
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def embed_once(texts: list[str]) -> np.ndarray:
    r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=600)
    if r.status_code >= 400:
        # 把服务端的错误正文带出来，否则只能看到 "400 Bad Request"
        raise RuntimeError("HTTP %d %s" % (r.status_code, (r.text or "")[:300]))
    return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)


BAD: list[str] = []


def embed_one_robust(t: str) -> np.ndarray:
    """单条文本：先原样，失败则逐档截断（服务端多半是嫌太长）。"""
    t = t if isinstance(t, str) else str(t)
    if not t.strip():
        t = "（空块）"
    for lim in (None, 6000, 3000, 1000, 200):
        s = t if lim is None else t[:lim]
        try:
            return embed_once([s])
        except Exception as exc:                                    # noqa: BLE001
            last = "%s（长度 %d%s）" % (exc, len(t), "" if lim is None else "，截断到 %d" % lim)
    BAD.append("%s ｜ 长度 %d ｜ 开头：%s" % (last, len(t), t[:60].replace("\n", " ")))
    return np.zeros((1, 1024), dtype=np.float32)


def embed_batch_robust(pairs: list[tuple[int, str]], dim: int) -> dict[int, np.ndarray]:
    """成批嵌入；遇到 400 就二分，最终退化到逐条（逐条再失败就截断）。

    pairs: [(行号, 文本)]，返回 {行号: 向量}。这样无论服务端是嫌"批量太大"还是
    "单条太长"，都能自己降级跑完，不会 30 分钟白跑。
    """
    out: dict[int, np.ndarray] = {}
    stack: list[list[tuple[int, str]]] = [pairs]
    while stack:
        cur = stack.pop()
        if not cur:
            continue
        try:
            arr = embed_once([t for _, t in cur])
            for k, (row, _) in enumerate(cur):
                out[row] = arr[k:k + 1]
        except Exception:                                           # noqa: BLE001
            if len(cur) == 1:
                row, t = cur[0]
                out[row] = embed_one_robust(t)
            else:
                mid = len(cur) // 2
                stack.append(cur[mid:])
                stack.append(cur[:mid])
    return out


def embed(texts: list[str], retries: int = 3) -> np.ndarray:
    """保留旧接口（测速/兼容用）。"""
    last = None
    for k in range(retries):
        try:
            return embed_once(texts)
        except Exception as exc:                                    # noqa: BLE001
            last = exc
            time.sleep(2 * (k + 1))
    raise last


def chunk_source(ing, path: Path, root: Path):
    """按入库同一套流程切块，返回 [(embed_text, meta), ...]。"""
    text = io.open(path, encoding="utf-8", errors="replace").read()
    fm, body = ing.split_okf(text)
    body = ing.normalize_body(body)
    if not body:
        return []
    out = []
    header = ing.context_header(fm)
    for ci, ch in enumerate(ing.chunk_by_paragraph(body)):
        meta = {
            "chunk_id": "%s#%d" % (path.relative_to(root).as_posix(), ci),
            "source": path.relative_to(root).as_posix(),
            "title": fm.get("title", ""), "type": fm.get("type", ""),
            "tags": fm.get("tags", []) or [], "issuer": fm.get("issuer", []) or [],
            "region_type": fm.get("region_type", ""), "region": fm.get("region", ""),
            "status": fm.get("status", ""), "standard_id": fm.get("standard_id", ""),
            "chunk_index": ci,
            "text": ("%s\n%s" % (header, ch)) if header else ch,
            "text_body": ch,
        }
        out.append((ing.make_embed_text(fm, ch), meta))
    return out


def scan_live():
    """扫线上 chunks.jsonl：来源顺序、每源的字节区间与向量行区间（假设同源连续）。"""
    order, spans = [], {}
    off = 0
    n = 0
    with io.open(SRC_IDX / "chunks.jsonl", "rb") as f:
        for raw in f:
            src = json.loads(raw.decode("utf-8")).get("source", "")
            if not order or order[-1] != src:
                order.append(src)
                spans[src] = {"byte": off, "rows": 0, "vec": n}
            spans[src]["rows"] += 1
            off += len(raw)
            n += 1
    total = n
    contiguous = sum(spans[s]["rows"] for s in order) == total and len(order) == len(spans)
    return order, spans, total, contiguous


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    ing = load(P6_INGEST, "ingest_p6")
    live = load(LIVE_INGEST, "ingest_live")
    t0 = time.time()
    print("P6 版 ingest：%s" % P6_INGEST)
    print("语料树：%s" % P6_TREE)

    order, spans, total, contiguous = scan_live()
    print("线上索引：%d 行 / %d 个来源；同源是否连续：%s" % (total, len(order), contiguous))
    if not contiguous:
        print("！线上行不是按来源连续分布的 —— 本脚本的「整段替换」前提不成立，先别跑")
        return 2

    md_of = {p.relative_to(P6_TREE).as_posix(): p for p in P6_TREE.rglob("*.md")}
    print("语料树 md：%d 份（线上有 %d 个来源）" % (len(md_of), len(order)))

    # ---------- 阶段 1：先只切块、数清楚要写多少行（不嵌入、不落盘） ----------
    print("\n阶段 1/4：切块计数（不嵌入）")
    new_counts, extra_sources = {}, []
    for i, src in enumerate(order, 1):
        p = md_of.get(src)
        if p is None:
            new_counts[src] = None              # 线上有、语料树没有 → 保留原样
            continue
        new_counts[src] = len(chunk_source(ing, p, P6_TREE))
        if i % 800 == 0:
            print("   已切 %d/%d ｜ %.0fs" % (i, len(order), time.time() - t0))
    for src in sorted(set(md_of) - set(order)):
        extra_sources.append(src)
        new_counts[src] = len(chunk_source(ing, md_of[src], P6_TREE))
    total_new = sum(v for v in new_counts.values() if v)
    print("   切块完成 %.0fs：线上 %d 行 → 新 %d 块（净增 %+d）；语料树多出的来源 %d 份"
          % (time.time() - t0, total, total_new, total_new - total, len(extra_sources)))
    if a.dry_run:
        print("\n【dry-run 结束】未嵌入、未落盘。")
        return 0

    # ---------- 阶段 2：逐源写 chunks.jsonl，同时填向量 ----------
    print("\n阶段 2/4：写 chunks.jsonl + 向量（未变行整段拷贝）")
    DST_IDX.mkdir(parents=True, exist_ok=True)
    live_vec = np.load(SRC_IDX / "vectors.npy", mmap_mode="r")
    assert live_vec.shape[0] == total, "线上向量行数 %d ≠ 文本行数 %d" % (live_vec.shape[0], total)
    # 续跑：若已有同形状的 vectors.npy，用 r+ 打开**不要截断**（否则前面嵌好的向量全丢）
    vec_path = DST_IDX / "vectors.npy"
    mode, reuse = "w+", False
    if vec_path.is_file():
        try:
            old = np.load(vec_path, mmap_mode="r")
            reuse = old.shape == (total_new, live_vec.shape[1])
            del old
        except Exception:                                           # noqa: BLE001
            reuse = False
        mode = "r+" if reuse else "w+"
    print("   向量文件：%s（%s）" % (vec_path.name, "续用已有" if reuse else "新建"))
    dst_vec = np.lib.format.open_memmap(vec_path, mode=mode,
                                        dtype=np.float32, shape=(total_new, live_vec.shape[1]))

    changed_src, unchanged_src = [], []
    to_embed: list[tuple[int, str]] = []          # (目标行号, embed 文本)
    row = 0
    t1 = time.time()
    with io.open(SRC_IDX / "chunks.jsonl", "rb") as fi, \
            io.open(DST_IDX / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as fo:
        for si, src in enumerate(order, 1):
            sp = spans[src]
            fi.seek(sp["byte"])
            old_rows = [json.loads(fi.readline().decode("utf-8")) for _ in range(sp["rows"])]
            p = md_of.get(src)
            new = chunk_source(ing, p, P6_TREE) if p is not None else []
            same = (len(new) == len(old_rows)
                    and all(nm["text"] == om.get("text") for (_, nm), om in zip(new, old_rows)))
            if same:
                unchanged_src.append(src)
                fi.seek(sp["byte"])
                for _ in range(sp["rows"]):
                    fo.write(fi.readline().decode("utf-8"))     # 逐字节原样
                # 向量整段切片拷贝
                for s in range(0, sp["rows"], VEC_SLICE):
                    e = min(s + VEC_SLICE, sp["rows"])
                    dst_vec[row + s:row + e] = live_vec[sp["vec"] + s:sp["vec"] + e]
                row += sp["rows"]
            else:
                changed_src.append(src)
                for et, meta in new:
                    fo.write(json.dumps(meta, ensure_ascii=False) + "\n")
                    to_embed.append((row, et))
                    row += 1
            if si % 400 == 0:
                print("   %d/%d 源 ｜ 已写 %d 行 ｜ 待嵌 %d ｜ %.0fs"
                      % (si, len(order), row, len(to_embed), time.time() - t1))

    for src in extra_sources:                     # 语料树新增的来源
        for et, meta in chunk_source(ing, md_of[src], P6_TREE):
            with io.open(DST_IDX / "chunks.jsonl", "a", encoding="utf-8", newline="\n") as fo:
                fo.write(json.dumps(meta, ensure_ascii=False) + "\n")
            to_embed.append((row, et))
            row += 1

    print("   写完：%d 行（依据切块计数应为 %d）；变更来源 %d ／ 沿用来源 %d；待嵌 %d"
          % (row, total_new, len(changed_src), len(unchanged_src), len(to_embed)))
    assert row == total_new, "行数对不上：写了 %d，预期 %d" % (row, total_new)

    # ---------- 阶段 3：嵌入变更行（健壮 + 可续跑） ----------
    print("\n阶段 3/4：嵌入 %d 块" % len(to_embed))
    prog_file = DST_IDX / "_embed_progress.json"
    start_at = 0
    if prog_file.is_file():
        try:
            pr = json.loads(prog_file.read_text(encoding="utf-8"))
            if pr.get("total") == len(to_embed):
                start_at = int(pr.get("done", 0))
                print("   ↩︎ 续跑：已完成 %d/%d，从第 %d 行继续" % (start_at, len(to_embed), start_at))
        except Exception as exc:                                    # noqa: BLE001
            print("   （进度文件读不了，从头嵌：%s）" % exc)
    t2 = time.time()
    done = start_at
    bs = BATCH
    for s in range(start_at, len(to_embed), bs):
        part = to_embed[s:s + bs]
        res = embed_batch_robust(part, live_vec.shape[1])
        for rr, v in res.items():
            dst_vec[rr] = v[0]
        done = s + len(part)
        if done % 3200 < bs or done == len(to_embed):
            el = time.time() - t2
            rate = (done - start_at) / el if el else 0
            print("   [%6d/%6d] %.1f 条/s · ETA %.1f min ｜ 本批 %d 条"
                  % (done, len(to_embed), rate,
                     (len(to_embed) - done) / rate / 60 if rate else 0, len(part)))
            dst_vec.flush()
            prog_file.write_text(json.dumps({"done": done, "total": len(to_embed),
                                             "at": time.strftime("%H:%M:%S")}), encoding="utf-8")
    dst_vec.flush()
    if BAD:
        print("   ⚠️ 有 %d 条文本连截断都嵌不了（已按零向量写入，需人工看）：" % len(BAD))
        for b in BAD[:5]:
            print("      %s" % b)
    print("   嵌入完成，用时 %.1f 分钟（本轮从 %d 开始）" % ((time.time() - t2) / 60, start_at))

    # ---------- 阶段 4：自检 ----------
    print("\n阶段 4/4：自检")
    # 4.1 未变更行抽样：向量应与线上逐字节一致
    import random
    rng = random.Random(20260922)
    keep_rows = []
    r = 0
    for src in order:
        if src in unchanged_src:
            keep_rows.extend(range(r, r + spans[src]["rows"]))
        r += (new_counts[src] if new_counts[src] is not None else spans[src]["rows"])
    sample = rng.sample(keep_rows, min(4000, len(keep_rows)))
    q = np.load(DST_IDX / "vectors.npy", mmap_mode="r")
    ok = all(np.array_equal(np.asarray(q[i]), np.asarray(live_vec[i])) for i in sample)
    print("   未变更行抽样 %d 条与线上向量逐字节一致：%s" % (len(sample), "✅" if ok else "❌"))

    # 4.2 关键探针：储油库 GB 20950 的限值数字
    def probe(needles, label):
        n = 0
        hit = None
        with io.open(DST_IDX / "chunks.jsonl", encoding="utf-8") as f:
            for line in f:
                if all(x in line for x in needles):
                    n += 1
                    hit = hit or json.loads(line)
        print("   %s：命中 %d 块 %s" % (label, n, "✅" if n else "❌"))
        if hit:
            print("      %s" % hit["text"][:150].replace("\n", " "))
    probe(["GB 20950", "≤25"], "储油库 GB 20950 含 ≤25")
    probe(["GB 20950", "≥95"], "储油库 GB 20950 含 ≥95")

    (DST_IDX / "meta.json").write_text(json.dumps({
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_index": str(SRC_IDX),
        "corpus_tree": str(P6_TREE),
        "ingest": P6_INGEST,
        "ingest_md5": hashlib.md5(Path(P6_INGEST).read_bytes()).hexdigest(),
        "chunks_total": total_new,
        "chunks_before": total,
        "chunks_added": len(to_embed),
        "sources_changed": len(changed_src),
        "sources_unchanged": len(unchanged_src),
        "note": "P6 表格单独成块 + 语料表格回填；未变更行 chunks 与向量逐字节沿用线上",
        "embed_recipe": "【title】 description\\n\\n<chunk_text>（与 ingest_okf.make_embed_text 一致）",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n完成，总用时 %.1f 分钟。新索引：%s" % ((time.time() - t0) / 60, DST_IDX))
    print("切换（人工确认后再执行）：bash /home/test/切换索引.sh %s" % DST_IDX)
    return 0


if __name__ == "__main__":
    sys.exit(main())
