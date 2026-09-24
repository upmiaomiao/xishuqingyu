#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建 index_v3：以已归一的 index_v2 为底，做两件增量改动。

为什么要增量（而不是用 ingest_okf.py 全量重建）：
  线上 index 的正文**带着 LaTeX 残留**（$1.0{\\times}10^{-5}$ 这类，占 6%），
  09-19 是靠 `建归一索引.py` 对索引做后处理才消掉的（index_v2）。
  如果现在从 md 全量重建，会把那个修复丢掉 —— 所以以 index_v2 为底：

  1. **标题修正**：235 份环评报告 md 的 front matter title 改过了（「环境影响报告书」→ 项目名）。
     入库配方是「【title】 description + 正文」，标题变了必须重嵌这些块。
  2. **新增文档**：okf_bundles 里索引中没有的 md（GB 18485-2014 / GB 18484-2020 本体），
     用与 ingest 完全相同的切块与配方追加；正文同样过一遍入库归一。
  3. **元数据（status）改写**（2026-09-22 加）：法规/标准被废止后要把 bundle 的 front matter
     `status: 现行` 改成 `已废止`，检索器按它降权（`retriever.py` ABOLISHED_PENALTY=0.35）。
     **但这一步原先做不了** —— 老逻辑只重写"标题变了"的行，status 变了的行会被**逐字节原样拷贝**，
     于是改了 bundle 也不生效、下次重建还会把补丁抹掉。
     现在加了这条分支：**只重写该行的 status，不重嵌** ——
     依据是线上 `ingest_okf.make_embed_text()` 的配方只有 `title` + `description`
     （函数体里 grep 不到 status/issuer/region/tags），status 不进嵌入文本，
     所以改它既不该、也不需要动向量。阶段 5 会**抽样逐字节核对**这些行的向量确实没变。
  4. **状态依据（status_note）改写**（2026-09-22 加）：光有"已废止"三个字不够。
     复测发现：给模型看了 `时效状态：已废止` 之后，固废法那条答对了，
     环评法那条却答成"元数据标注为已废止，但该标注与正文记载不一致，**可能是录入错误**" ——
     因为环评报告里还在引用它，而元数据没给出**依据**。
     所以把 front matter 里的 status_note（法典第1242条／被哪个新标准代替）也同步进索引，
     提示词才能写出「已废止（依据：……）」。与 status 同类：纯元数据，不重嵌。

用法：
  python 建索引v3.py --dry-run    # 只统计要改/要加多少，不写文件、不 embedding
  python 建索引v3.py --src /data/fagui_rag/index --dst /data/fagui_rag/index_v4_status   # 真建
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
import yaml

SRC = Path("/data/fagui_rag/index_v2")
DST = Path("/data/fagui_rag/index_v3")
BUNDLE = Path("/data/fagui_rag/okf_bundles")
EMB = "http://127.0.0.1:34004/v1/embeddings"
BATCH = 32
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 入库脚本（切块规则/配方都在这里）；INDEX_DIR 指到 v3，避免它 import 时碰线上目录
os.environ.setdefault("INDEX_DIR", str(DST))
ing = load_module("ingest_okf", "/data/fagui_rag/ingest_okf.py")
tc = load_module("textclean", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")


def embed(texts: list[str], retries: int = 3) -> np.ndarray:
    last = None
    for k in range(retries):
        try:
            r = requests.post(EMB, json={"model": "BGE-M3", "input": texts}, timeout=300)
            r.raise_for_status()
            return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
        except Exception as e:
            last = e
            time.sleep(2 * (k + 1))
    raise last


def fm_of(src: str, cache: dict) -> dict:
    if src not in cache:
        p = BUNDLE / src
        if p.is_file():
            m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8", errors="replace"))
            try:
                cache[src] = (yaml.safe_load(m.group(1)) or {}) if m else {}
            except Exception:
                cache[src] = {}
        else:
            cache[src] = {}
    return cache[src]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--src", default=str(SRC), help="底索引目录（默认 index_v2，已归一）")
    ap.add_argument("--dst", default=str(DST), help="输出索引目录")
    ap.add_argument("--allow-stale-src", action="store_true",
                    help="底索引块数少于线上时也允许执行（默认拒绝，防止把线上回退）")
    args = ap.parse_args()
    src_dir, dst_dir = Path(args.src), Path(args.dst)
    if src_dir.resolve() == dst_dir.resolve():
        raise SystemExit("--src 与 --dst 不能是同一个目录")

    # 防呆（2026-09-22 实测踩过）：`SRC` 默认仍是旧的 index_v2（265k 块）。
    # P6 上线后线上是 356k 块，若照默认值真跑，会把 P6 的成果**回退**成 265k。
    # 所以：底索引块数明显小于线上 /data/fagui_rag/index 时，**拒绝执行**，除非显式加 --allow-stale-src。
    live = Path("/data/fagui_rag/index")
    if not args.allow_stale_src and live.is_dir() and src_dir.resolve() != live.resolve():
        def _count(d: Path) -> int:
            f = d / "chunks.jsonl"
            if not f.is_file():
                return -1
            with open(f, encoding="utf-8") as fh:
                return sum(1 for _ in fh)

        n_src, n_live = _count(src_dir), _count(live)
        if 0 <= n_src < n_live:
            raise SystemExit(
                "拒绝执行：底索引 %s 只有 %d 块，而线上 %s 有 %d 块。\n"
                "  照此运行会把线上索引**回退**掉。若确实要以它为底，请加 --allow-stale-src；\n"
                "  正常增量请写：--src /data/fagui_rag/index --dst <新目录>"
                % (src_dir, n_src, live, n_live))
        print("  底索引 %s：%d 块（线上 %s：%d 块）" % (src_dir, n_src, live, n_live))

    t0 = time.time()
    dst_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 阶段 1：现有的块，找出标题变了的 ----------
    print("阶段 1/5：读 index_v2，比对标题")
    lines: list[str] = []
    objs: list[dict] = []
    with open(src_dir / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            lines.append(line)
            objs.append(json.loads(line))
    total = len(objs)
    print(f"   现有 {total:,} 块")

    fm_cache: dict = {}
    retitle: list[tuple[int, dict, str]] = []      # (行号, 块, 新标题)
    restatus: list[tuple[int, dict, str]] = []     # (行号, 块, 新状态) —— 只改元数据，不重嵌
    renotes: list[tuple[int, dict, str]] = []      # (行号, 块, 新状态依据) —— 同上，只改元数据
    missing_src = 0
    for i, o in enumerate(objs):
        src = o.get("source") or ""
        fm = fm_of(src, fm_cache)
        if not fm and not (BUNDLE / src).is_file():
            missing_src += 1
            continue
        new_t = (fm.get("title") or "").strip() if isinstance(fm.get("title"), str) else ""
        old_raw = o.get("title")                      # 索引里有 NaN(float) 型标题
        old_t = old_raw.strip() if isinstance(old_raw, str) else ""
        if new_t and new_t != old_t:
            retitle.append((i, o, new_t))
        # 状态（现行/已废止）：不算"标题变更"，单独走一条只写元数据的分支
        new_s = (fm.get("status") or "").strip() if isinstance(fm.get("status"), str) else ""
        old_s = o.get("status") or ""
        old_s = old_s.strip() if isinstance(old_s, str) else ""
        if new_s and new_s != old_s:
            restatus.append((i, o, new_s))
        # 状态依据（status_note）：**为什么废止**。2026-09-22 加。
        # 起因：只把 status 改成"已废止"之后复测，固废法那条答对了，环评法那条却答成
        #   "元数据标注为已废止，但该标注与法律正文记载不一致，可能是录入错误" ——
        #   光有一个标记、没有依据，模型宁可相信环评报告里的引用，也不信这个标记。
        #   所以把 front matter 里那句依据（法典第1242条／被哪个新标准代替）也同步进索引，
        #   提示词里就能写出「已废止（依据：……）」。
        new_n = (fm.get("status_note") or "").strip() if isinstance(fm.get("status_note"), str) else ""
        old_n = o.get("status_note") or ""
        old_n = old_n.strip() if isinstance(old_n, str) else ""
        if new_n and new_n != old_n:
            renotes.append((i, o, new_n))
    print(f"   标题需更新 {len(retitle):,} 块（涉及 "
          f"{len({o.get('source') for _, o, _ in retitle}):,} 份文档）；"
          f"状态需更新 {len(restatus):,} 块（涉及 "
          f"{len({o.get('source') for _, o, _ in restatus}):,} 份文档，只写元数据不重嵌）；"
          f"状态依据需补 {len(renotes):,} 块（涉及 "
          f"{len({o.get('source') for _, o, _ in renotes}):,} 份文档，同样不重嵌）；"
          f"源文件已不在语料 {missing_src} 块")
    if restatus:
        st_of = {}
        for _, o, s in restatus:
            src = (o.get("source") or "")[:70]
            st_of.setdefault(src, []).append(f"{(o.get('status') or '(空)')}→{s}")
        print("   状态改写清单（前 20 份）：")
        for k, v in list(st_of.items())[:20]:
            print(f"     {v[0]}  ×{len(v):>3} 块  {k}")

    # ---------- 阶段 2：新文档（索引里没有的 md） ----------
    print("\n阶段 2/5：找出新文档并切块")
    have = {o.get("source") for o in objs}
    new_mds = [p for p in sorted(BUNDLE.rglob("*.md"))
               if p.relative_to(BUNDLE).as_posix() not in have]
    print(f"   新文档 {len(new_mds)} 份")
    new_metas: list[dict] = []
    new_embed_texts: list[str] = []
    for md in new_mds:
        text = md.read_text(encoding="utf-8", errors="replace")
        fm, body = ing.split_okf(text)
        body = ing.normalize_body(body)
        if not body:
            continue
        for ci, ch in enumerate(ing.chunk_by_paragraph(body)):
            ch_norm = tc.clean_retrieved_text(ch)        # 与 index_v2 一致的入库归一
            meta = {
                "chunk_id": f"{md.relative_to(BUNDLE).as_posix()}#{ci}",
                "source": md.relative_to(BUNDLE).as_posix(),
                "title": fm.get("title", ""),
                "type": fm.get("type", ""),
                "tags": fm.get("tags", []) or [],
                "issuer": fm.get("issuer", []) or [],
                "region_type": fm.get("region_type", ""),
                "region": fm.get("region", ""),
                "status": fm.get("status", ""),
                "standard_id": fm.get("standard_id", ""),
                "chunk_index": ci,
                "text": ch_norm,
            }
            new_metas.append(meta)
            new_embed_texts.append(ing.make_embed_text(fm, ch_norm))
    print(f"   新文档共切出 {len(new_metas)} 块")
    for md in new_mds:
        rel = md.relative_to(BUNDLE).as_posix()
        n = sum(1 for m in new_metas if m["source"] == rel)
        print(f"     + {n:>4} 块  {rel[:96]}")

    print(f"\n小结：标题重嵌 {len(retitle):,} 块；状态改写 {len(restatus):,} 块、"
          f"状态依据补写 {len(renotes):,} 块（都不重嵌）；"
          f"新增 {len(new_metas):,} 块；总块数 {total:,} → {total + len(new_metas):,}")
    if args.dry_run:
        print("\n【dry-run】未写文件、未 embedding。")
        return 0

    # ---------- 阶段 3：写 chunks.jsonl ----------
    # 三件事都落在这里：标题变了要重写该行（后面会重嵌），
    # 状态/状态依据变了**也只重写该行**（纯元数据，不进嵌入配方）。
    # 一行同时命中多项时，字段一起改。
    print("\n阶段 3/5：写 chunks.jsonl")
    new_title_by_row = {i: t for i, _, t in retitle}
    new_status_by_row = {i: s for i, _, s in restatus}
    new_note_by_row = {i: n for i, _, n in renotes}
    with open(dst_dir / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as fo:
        for i, (line, o) in enumerate(zip(lines, objs)):
            nt = new_title_by_row.get(i)
            ns = new_status_by_row.get(i)
            nn = new_note_by_row.get(i)
            if nt is not None or ns is not None or nn is not None:
                o2 = dict(o)
                if nt is not None:
                    o2["title"] = nt
                if ns is not None:
                    o2["status"] = ns
                if nn is not None:
                    o2["status_note"] = nn
                fo.write(json.dumps(o2, ensure_ascii=False) + "\n")
            else:
                fo.write(line)
        for m in new_metas:
            fo.write(json.dumps(m, ensure_ascii=False) + "\n")

    # ---------- 阶段 4：向量 ----------
    print("\n阶段 4/5：拷向量 → 重算变更行 → 追加新块向量")
    print(f"   说明：{len(restatus):,} 块只改了 status，**不重嵌**（status 不进嵌入配方），"
          f"这些行直接沿用原向量")
    vecs = np.load(src_dir / "vectors.npy", mmap_mode="r")
    assert vecs.shape[0] == total, f"行数对不上：{vecs.shape[0]} vs {total}"
    out = np.zeros((total + len(new_metas), 1024), dtype=np.float32)
    out[:total] = np.asarray(vecs)
    del vecs
    np.save(dst_dir / "vectors.npy", out)
    out = np.load(dst_dir / "vectors.npy", mmap_mode="r+")

    todo: list[tuple[int, str]] = []          # (行号, 待 embed 文本)
    for i, o, new_t in retitle:
        fm = fm_of(o.get("source") or "", fm_cache)
        fm2 = dict(fm)
        fm2["title"] = new_t                   # 用新标题算配方前缀
        todo.append((i, ing.make_embed_text(fm2, o.get("text") or "")))
    for k, t in enumerate(new_embed_texts):
        todo.append((total + k, t))

    print(f"   待重算 {len(todo):,} 条")
    t1 = time.time()
    done = 0
    for s in range(0, len(todo), BATCH):
        batch = todo[s:s + BATCH]
        arr = embed([t for _, t in batch])
        for k, (row, _) in enumerate(batch):
            out[row] = arr[k]
        done += len(batch)
        if done % 3200 < BATCH:
            el = time.time() - t1
            rate = done / el if el else 0
            print(f"   [{done:>6}/{len(todo)}] {rate:.1f} 条/s · "
                  f"ETA {(len(todo) - done) / rate / 60 if rate else 0:.1f} min")
    out.flush()
    print(f"   完成，用时 {(time.time() - t1) / 60:.1f} 分钟")

    # ---------- 阶段 5：自检 ----------
    print("\n阶段 5/5：自检")
    v1 = np.load(src_dir / "vectors.npy", mmap_mode="r")
    v3 = np.load(dst_dir / "vectors.npy", mmap_mode="r")
    changed_rows = {r for r, _ in todo}
    rng = np.random.default_rng(0)
    untouched = [i for i in rng.choice(total, size=4000, replace=False) if i not in changed_rows]
    same = all(np.array_equal(np.asarray(v1[i]), np.asarray(v3[i])) for i in untouched)
    print(f"   未变更行抽样 {len(untouched)} 条向量逐字节一致：{'✅' if same else '❌'}")
    retitled_rows = sorted(changed_rows & set(range(total)))
    if retitled_rows:
        sample = list(rng.choice(retitled_rows, size=min(200, len(retitled_rows)),
                                 replace=False))
        differ = sum(1 for i in sample
                     if not np.array_equal(np.asarray(v1[i]), np.asarray(v3[i])))
        print(f"   标题重嵌行抽样 {len(sample)} 条中确有新向量：{differ}/{len(sample)} "
              f"{'✅' if differ >= len(sample) * 0.975 else '❌'}")
    else:
        print("   本次没有标题重嵌行（0 条），跳过该抽样")
    # 只改状态的这批：向量**必须**与底索引逐字节一致（没重嵌），这是"改元数据没动向量"的证据
    # （status_note 与 status 同类：都不进嵌入配方，所以并进同一批抽样）
    only_restatus = sorted(({r for r, _, _ in restatus} | {r for r, _, _ in renotes}) - changed_rows)
    if only_restatus:
        sample = list(rng.choice(only_restatus, size=min(300, len(only_restatus)),
                                 replace=False))
        same2 = sum(1 for i in sample
                    if np.array_equal(np.asarray(v1[i]), np.asarray(v3[i])))
        print(f"   仅元数据变更行抽样 {len(sample)} 条向量逐字节未变：{same2}/{len(sample)} "
              f"{'✅' if same2 == len(sample) else '❌'}")
    if new_metas:
        zeros = sum(1 for i in range(total, total + len(new_metas))
                    if not np.any(np.asarray(v3[i])))
        print(f"   新增 {len(new_metas)} 块的向量为全零的：{zeros} "
              f"{'✅' if zeros == 0 else '❌'}")

    # 新标准块：文本里有 18485 限值表吗
    checks = {"GB 18485": 0, "GB 18484": 0, "850": 0, "0.1 ng": 0}
    with open(dst_dir / "chunks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if "18485" in line:
                checks["GB 18485"] += 1
            if "18484" in line:
                checks["GB 18484"] += 1
    for m in new_metas:
        t = m["text"]
        if "850" in t:
            checks["850"] += 1
        if "0.1 ng" in t or "0.1ng" in t:
            checks["0.1 ng"] += 1
    print(f"   全库含「18485」的块 {checks['GB 18485']}；含「18484」的块 {checks['GB 18484']}；"
          f"新块里含「850」{checks['850']} 条、含「0.1 ng」{checks['0.1 ng']} 条")
    n_title_ok = sum(1 for m in new_metas if m["title"])
    print(f"   新块标题齐全：{n_title_ok}/{len(new_metas)}")

    # 状态改写到底落盘没有：从**刚写出的** chunks.jsonl 里按来源重新数一遍
    if restatus:
        want = {}
        for _, o, s in restatus:
            want.setdefault(o.get("source"), set()).add(s)
        got = {k: {} for k in want}
        with open(dst_dir / "chunks.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                sr = o.get("source")
                if sr in got:
                    st = o.get("status") or "(空)"
                    got[sr][st] = got[sr].get(st, 0) + 1
        bad = []
        for sr, sts in want.items():
            g = got[sr]
            if set(g) != sts:
                bad.append((sr, sts, g))
        print(f"   落盘复核：{len(want)} 份文档的 status 已全部改写为 {sorted({s for _, _, s in restatus})}"
              f" {'✅' if not bad else '❌ ' + str(bad[:3])}")
        for sr, g in list(got.items())[:12]:
            print(f"     {dict(g)}  {sr[:80]}")

    # 状态依据到底落盘没有：同样从**刚写出的** chunks.jsonl 重新数
    if renotes:
        want_n = {}
        for _, o, n in renotes:
            want_n.setdefault(o.get("source"), set()).add(n)
        got_n = {k: set() for k in want_n}
        with open(dst_dir / "chunks.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                sr = o.get("source")
                if sr in got_n:
                    got_n[sr].add(o.get("status_note") or "")
        bad_n = [sr for sr, ns in want_n.items() if not ns <= got_n.get(sr, set())]
        print(f"   落盘复核：{len(want_n)} 份文档的 status_note 已写入 "
              f"{'✅' if not bad_n else '❌ ' + str(bad_n[:3])}")
        for sr, ns in list(want_n.items())[:6]:
            note = next(iter(ns))
            print(f"     {note[:96]}  ← {sr[:56]}")

    (dst_dir / "meta.json").write_text(json.dumps({
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_index": str(src_dir),
        "chunks_total": total + len(new_metas),
        "chunks_retitled": len(retitle),
        "chunks_restatus": len(restatus),
        "chunks_restatus_note": len(renotes),
        "restatus_sources": sorted({o.get("source") for _, o, _ in restatus})[:20],
        "note_sources": sorted({o.get("source") for _, o, _ in renotes})[:20],
        "chunks_added": len(new_metas),
        "added_sources": [m["source"] for m in new_metas][:5],
        "embed_recipe": "【title】 description\\n\\n<chunk_text>（与 ingest_okf.py 一致）",
        "normalizer": "xishu_pipeline/textclean.py::clean_retrieved_text（沿用 index_v2）",
        "textclean_md5": hashlib.md5(Path(tc.__file__).read_bytes()).hexdigest(),
        "note": "以底索引用增量：标题修正重嵌 + 标准本体追加 + status/status_note 元数据改写"
                "（纯元数据不进嵌入配方，不重嵌）；未变更行向量逐字节沿用",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成，总用时 {(time.time() - t0) / 60:.1f} 分钟 → {dst_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
