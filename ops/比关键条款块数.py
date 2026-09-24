#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""切换前最后一次数据层核对：新旧索引里"关键条款原文"各有多少块（不调模型）。

为什么要它：B1–B5 复测里 B5 没通过（两边都没过）。要区分"新索引把材料弄丢了"与
"两边都只是没召回"——直接数原文块最干脆：
  · 「车间或车间处理设施排放口」= GB 8978-1996 第一类污染物采样口那句；
  · 「第一类污染物」、总汞 0.05 —— 周边证据。
新索引里这些块**只应更多**（回填补了正文），如果反而变少，那才是真问题。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

IDX = {"线上 index": Path("/data/fagui_rag/index"),
       "新 index_p6": Path("/data/fagui_rag/index_p6")}
NEEDLES = ["车间或车间处理设施排放口", "第一类污染物", "总汞", "0.05"]


def main() -> int:
    print("%-16s %s" % ("索引", "  ".join("%-14s" % n for n in NEEDLES)))
    for tag, d in IDX.items():
        f = d / "chunks.jsonl"
        if not f.is_file():
            print("%-16s 无 chunks.jsonl" % tag)
            continue
        cnt = {n: 0 for n in NEEDLES}
        gb = {n: 0 for n in NEEDLES}          # 限定在 GB 8978 的块里
        total = 0
        with io.open(f, encoding="utf-8") as fh:
            for line in fh:
                total += 1
                for n in NEEDLES:
                    if n in line:
                        cnt[n] += 1
                        if "8978" in line:
                            gb[n] += 1
        print("%-16s %s   （共 %d 块）" % (tag, "  ".join("%-14d" % cnt[n] for n in NEEDLES), total))
        print("%-16s %s   ← 限定 GB 8978 的块" % ("", "  ".join("%-14d" % gb[n] for n in NEEDLES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
