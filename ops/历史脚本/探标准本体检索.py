#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：垃圾焚烧标准本体类问题的检索与作答（换语料前 / 后各跑一次做对照）。

看三件事：
  1. 引用里有没有「点名的标准本体」（standard_id 命中）；
  2. 答案里有没有关键限值数字；
  3. rerank 最高分与引用构成。

用法：python 探标准本体检索.py 换语料前
输出：_工作记录/探标准_<标签>.json
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SITE = "http://10.201.31.10:8011/hybrid_search"

QS = [
    ("18485-限值", "GB 18485-2014 生活垃圾焚烧污染控制标准规定的颗粒物、氮氧化物、"
                   "二氧化硫、氯化氢排放限值分别是多少？"),
    ("18485-技术性能", "生活垃圾焚烧炉的技术性能要求是什么？炉膛温度、烟气停留时间、"
                       "炉渣热灼减率分别有什么规定？"),
    ("18484-限值", "GB 18484-2020 危险废物焚烧污染控制标准对烟气中重金属、二噁英类的"
                   "排放限值是多少？"),
    ("飞灰处置", "生活垃圾焚烧产生的飞灰应该按什么标准处理处置？有哪些要求？"),
]
# 每个问题期望在答案里出现的关键数字
EXPECT = {
    "18485-限值": ["30", "20", "300", "250", "100", "50", "60"],
    "18485-技术性能": ["850", "2", "5%", "5 %"],
    "18484-限值": ["0.1", "0.5", "ng", "mg"],
    "飞灰处置": ["HJ 1134", "1134", "螯合", "填埋", "GB 16889"],
}


def ask(q: str, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                SITE, data=json.dumps({"query": q}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))
        except Exception as e:                      # 连接被掐断/超时都重试
            last = e
            print(f"    （第 {i + 1} 次失败：{type(e).__name__}: {e}，10s 后重试）")
            time.sleep(10)
    raise SystemExit(f"连续 {tries} 次都没问通：{last}")


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "未标注"
    out = []
    for tag, q in QS:
        d = ask(q)
        srcs = d.get("sources") or []
        ans = d.get("answer") or ""
        std_hits = []
        for s in srcs:
            sid = str(s.get("standard_id") or "")
            title = str(s.get("title") or "")
            if re.search(r"18485|18484", sid + title):
                std_hits.append(f"{sid or title[:24]}")
        expect_hit = [k for k in EXPECT[tag] if k in ans]
        rr = [s.get("rerank_score") or 0 for s in srcs]
        rec = {
            "标签": tag, "问题": q, "route": d.get("route"),
            "耗时s": d.get("latency_s"), "答案字数": len(ans),
            "引用数": len(srcs),
            "rerank最高": round(max(rr), 3) if rr else None,
            "本体命中": std_hits,
            "答案里的期望数字": expect_hit,
            "缺的数字": [k for k in EXPECT[tag] if k not in ans],
            "引用": [{"i": s.get("index"), "type": s.get("doc_type"),
                      "status": s.get("status"), "standard_id": s.get("standard_id"),
                      "rerank": round(s.get("rerank_score") or 0, 3),
                      "title": str(s.get("title"))[:60]} for s in srcs],
            "答案": ans,
        }
        out.append(rec)
        print(f"\n【{label}】{tag}  route={rec['route']} {rec['耗时s']}s "
              f"引用{rec['引用数']}条 rerank最高={rec['rerank最高']} 答案{rec['答案字数']}字")
        print(f"   本体命中：{std_hits or '（无）'}")
        print(f"   答案含期望数字 {len(expect_hit)}/{len(EXPECT[tag])}；"
              f"缺：{rec['缺的数字']}")
        for s in rec["引用"]:
            print(f"     [{s['i']}] {str(s['type']):<9} {str(s['status'] or ''):<5} "
                  f"{(s['standard_id'] or ''):<14} {s['rerank']:.3f}  {s['title'][:44]}")

    p = WS / "_工作记录" / f"探标准_{label}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
