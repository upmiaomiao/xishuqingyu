#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换索引后的回归抽查：重跑指定题号，与基线（实跑20条_输出v2.jsonl）逐项对照。

看四件事：
  1. 引用标题是不是从「环境影响报告书」变成了项目名（标题修正的效果）；
  2. 引用数与 rerank 最高分有没有明显退化；
  3. 答案字数有没有异常（大幅缩水 = 拒答，大幅膨胀 = 自由发挥）；
  4. 点名的标准（GB 18485 等）有没有进引用。

用法：python 回归抽查.py 4 5 7 8 13 15 16 17
输出：_工作记录/回归抽查_<时间戳>.json
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SITE = "http://10.201.31.10:8011/hybrid_search"
BASE = WS / "_工作记录" / "实跑20条_输出v2.jsonl"


def ask(q: str, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                SITE, data=json.dumps({"query": q}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=900).read().decode("utf-8"))
        except Exception as e:
            last = e
            print(f"    （第 {i + 1} 次失败：{type(e).__name__}，10s 后重试）")
            time.sleep(10)
    raise SystemExit(f"连续 {tries} 次都没问通：{last}")


def main() -> int:
    want = [int(x) for x in sys.argv[1:]] or [4, 5, 7, 8, 13, 15, 16, 17]
    items = {json.loads(l)["序号"]: json.loads(l) for l in
             io.open(WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl", encoding="utf-8")}
    base = {json.loads(l)["序号"]: json.loads(l) for l in
            io.open(BASE, encoding="utf-8") if l.strip()}

    out = []
    for no in want:
        it = items[no]
        d = ask(it["题目"])
        srcs = d.get("sources") or []
        ans = d.get("answer") or ""
        b = base.get(no) or {}
        b_srcs = b.get("引用") or []
        rr = [s.get("rerank_score") or 0 for s in srcs]
        b_rr = [s.get("rerank_score") or 0 for s in b_srcs]
        rec = {
            "序号": no, "题型": it["题型"], "耗时s": d.get("latency_s"),
            "答案字数": len(ans), "基线答案字数": len(b.get("答案") or ""),
            "引用数": len(srcs), "基线引用数": len(b_srcs),
            "rerank最高": round(max(rr), 3) if rr else None,
            "基线rerank最高": round(max(b_rr), 3) if b_rr else None,
            "标题有辨识度的引用": sum(1 for s in srcs
                                      if len(str(s.get("title") or "")) >= 12),
            "引用": [{"i": s.get("index"), "type": s.get("doc_type"),
                      "status": s.get("status"), "standard_id": s.get("standard_id"),
                      "rerank": round(s.get("rerank_score") or 0, 3),
                      "title": str(s.get("title"))[:70]} for s in srcs],
            "答案": ans,
        }
        out.append(rec)
        print(f"\n#{no} {it['题型']}  {rec['耗时s']}s  引用 {rec['引用数']}（基线 {rec['基线引用数']}）"
              f"  rerank最高 {rec['rerank最高']}（基线 {rec['基线rerank最高']}）")
        print(f"   答案 {rec['答案字数']} 字（基线 {rec['基线答案字数']}）；"
              f"标题≥12字的引用 {rec['标题有辨识度的引用']}/{rec['引用数']}")
        for s in rec["引用"]:
            print(f"     [{s['i']}] {str(s['type']):<9} {str(s['status'] or ''):<5} "
                  f"{s['rerank']:.3f}  {s['title'][:56]}")

    p = WS / "_工作记录" / f"回归抽查_{time.strftime('%Y%m%d_%H%M')}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
