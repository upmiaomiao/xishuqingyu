#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验 index_v3：块数/向量、标题改善、LaTeX 不回归、新标准是否在库。

用法：python 查索引v3质量.py [索引目录]（默认 /data/fagui_rag/index_v3）
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

IDX = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index_v3")
LIVE = Path("/data/fagui_rag/index")

LATEX = {"mathrm": re.compile(r"\\mathrm"), "times": re.compile(r"\\times"),
         "dollar": re.compile(r"\$"), "frac": re.compile(r"\\frac")}
GENERIC = {"环境影响报告书", "环境影响报告书 （信息公开版）", "建设项目环境影响报告表",
           "一、建设项目基本情况", "《建设项目环境影响报告表》编制说明",
           "进行环境影响评价并公示环境影响报告书。本环境影响报告书第三章部分监测数据、第",
           "工程咨询证书编号：工咨甲12120070023 工程号：环06-2017-22"}


def stats(d: Path, label: str) -> dict:
    n = 0
    titles = Counter()
    latex = Counter()
    empty_title = 0
    types = Counter()
    with open(d / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            n += 1
            o = json.loads(line)
            t = o.get("title")
            if not isinstance(t, str) or not t.strip():
                empty_title += 1
            else:
                titles[t.strip()[:40]] += 1
            types[o.get("type") or "（空）"] += 1
            txt = o.get("text") or ""
            for k, p in LATEX.items():
                if p.search(txt):
                    latex[k] += 1
    v = np.load(d / "vectors.npy", mmap_mode="r")
    print(f"\n=== {label}（{d}）===")
    print(f"  chunks={n:,}  vectors={v.shape}  "
          f"{'✅' if v.shape[0] == n else '❌ 不一致'}")
    print(f"  类型分布：{dict(types.most_common(8))}")
    gen = sum(c for t, c in titles.items() if t in GENERIC)
    print(f"  **无辨识度标题的块：{gen:,}**（空标题 {empty_title:,}）")
    print("  最常见的 6 个标题：")
    for t, c in titles.most_common(6):
        print(f"    {c:>7,}  {t}")
    print("  LaTeX 残留：" + "  ".join(f"{k}={v:,}" for k, v in latex.items()))
    return {"n": n, "generic": gen, "empty": empty_title, "latex": dict(latex),
            "titles": titles}


def main() -> int:
    a = stats(LIVE, "线上 index（对照）")
    b = stats(IDX, "新索引")
    print("\n=== 对比结论 ===")
    print(f"  块数：{a['n']:,} → {b['n']:,}（差 {b['n'] - a['n']:+,}）")
    print(f"  无辨识度标题：{a['generic']:,} → {b['generic']:,} "
          f"（{'✅ 改善' if b['generic'] < a['generic'] else '❌ 没改善'}）")
    print(f"  空标题：{a['empty']:,} → {b['empty']:,}")
    for k in LATEX:
        print(f"  LaTeX {k}：{a['latex'].get(k, 0):,} → {b['latex'].get(k, 0):,} "
              f"（线上残留说明这份底索引没归一；新索引应当为 0）")

    # 新标准在不在
    print("\n=== 新标准是否在库 ===")
    hits = {"18485": [], "18484": []}
    with open(IDX / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            for k in hits:
                if k in line and len(hits[k]) < 3:
                    o = json.loads(line)
                    if k in (str(o.get("standard_id")) + str(o.get("source"))):
                        hits[k].append(o)
    for k, arr in hits.items():
        print(f"  GB {k}：{'✅ ' + str(len(arr)) + ' 条样例' if arr else '❌ 库里没有'}")
        for o in arr:
            print(f"     standard_id={o.get('standard_id')} status={o.get('status')} "
                  f"title={str(o.get('title'))[:40]}")
            print(f"       {o['text'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
