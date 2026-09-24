#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补 12 条垃圾焚烧题线上实跑（字段与 验20条_线上实跑v2.py 完全一致，便于同一套核验/判分）。

用法：python 验补12条_线上实跑.py [--only 21,22]
输入：_工作记录/垃圾焚烧好题型_补12条.jsonl
输出：_工作记录/实跑补12条_输出.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
IN = WS / "_工作记录" / "垃圾焚烧好题型_补12条.jsonl"
OUT = WS / "_工作记录" / "实跑补12条_输出.jsonl"
BASE = "http://10.201.31.10:8011"
RE_STD = re.compile(r"\b(GB|HJ|DB\d{2}|HG|JB|CJJ|CJ|NY|DL)\s*/?\s*[TZ]?\s*\d{2,5}(?:[.—\-－]\d{2,4})?", re.I)

KEEP = ("index", "title", "source", "text", "rerank_score", "vector_score",
        "standard_id", "doc_type", "status", "issuer", "region", "chunk_index")


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ask(q: str, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        BASE + "/hybrid_search",
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def stds(text: str) -> set[str]:
    return {" ".join(m.group(0).split()).upper().replace("—", "-").replace("－", "-")
            for m in RE_STD.finditer(text or "")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None

    items = [r for r in load(IN) if only is None or r["序号"] in only]
    print(f"实跑 {len(items)} 条（补题）→ {BASE}/hybrid_search\n" + "=" * 104, flush=True)
    rows = []
    for it in items:
        q = it["题目"]
        t0 = time.time()
        try:
            d = ask(q)
            err = ""
        except urllib.error.HTTPError as e:
            d, err = {}, f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            d, err = {}, f"{type(e).__name__}: {e}"
        dt = time.time() - t0
        ans = d.get("answer") or ""
        srcs = [{k: s.get(k) for k in KEEP} for s in (d.get("sources") or [])]
        q_std = stds(q)
        hit_body, hit_meta = set(), set()
        for s in srcs:
            body = f"{s.get('text') or ''} {s.get('title') or ''}"
            hit_body |= q_std & stds(body)
            hit_meta |= q_std & stds(f"{s.get('standard_id') or ''} {s.get('title') or ''}")
        dts = Counter(s.get("doc_type") or "?" for s in srcs)
        rr = [s.get("rerank_score") for s in srcs
              if isinstance(s.get("rerank_score"), (int, float))]
        titles = [s.get("title") or "" for s in srcs]
        rec = {
            "序号": it["序号"], "题型": it["题型"], "工艺域": it.get("工艺域"),
            "主补域": it.get("主补域"), "语言": it.get("语言", "中文"), "题目": q,
            "error": err, "耗时s": round(dt, 1), "route": d.get("route"),
            "model": d.get("model"), "usage": d.get("usage"), "站点latency_s": d.get("latency_s"),
            "答案": ans, "答案字数": len(ans), "reasoning": d.get("reasoning") or "",
            "引用条数": len(srcs), "引用": srcs,
            "doc_type分布": dict(dts),
            "依据类条数": sum(v for k, v in dts.items() if k in ("standard", "law", "guideline")),
            "案例类条数": dts.get("report", 0),
            "标题重复数": len(titles) - len(set(titles)),
            "rerank_top1": max(rr) if rr else None,
            "rerank_mean": round(sum(rr) / len(rr), 4) if rr else None,
            "题目中的标准号": sorted(q_std),
            "引用正文命中的标准号": sorted(hit_body),
            "引用标题命中的标准号": sorted(hit_meta),
        }
        rows.append(rec)
        print(f"{'✅' if not err else '❌'} [{it['序号']:>2}] {it['题型'][:12]:<12} {dt:>5.0f}s  "
              f"答案 {len(ans):>5} 字  引用 {len(srcs):>2} {dict(dts)}  "
              f"rerank {rec['rerank_top1'] if rec['rerank_top1'] is None else round(rec['rerank_top1'], 3)}  "
              f"{err}", flush=True)

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    ok = [r for r in rows if not r["error"]]
    print("\n" + "=" * 104)
    if ok:
        print(f"成功 {len(ok)}/{len(rows)}　平均 {sum(r['耗时s'] for r in ok) / len(ok):.0f}s　"
              f"平均引用 {sum(r['引用条数'] for r in ok) / len(ok):.1f}　"
              f"平均字数 {sum(r['答案字数'] for r in ok) / len(ok):.0f}　"
              f"标题重复合计 {sum(r['标题重复数'] for r in ok)}")
    print(f"→ {OUT.relative_to(WS)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
