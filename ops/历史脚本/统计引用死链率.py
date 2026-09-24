#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确统计：索引里每条来源的 .md 是否能在 PDF_ROOT 下找到同名 .pdf。

直接读 chunks.jsonl（不调模型），得到"引用卡片死链率"的确定值。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

INDEX = Path("/data/fagui_rag/index/chunks.jsonl")
PDF_ROOT = Path("/data/fagui_pdf")


def main():
    src_chunks = Counter()          # source -> chunk 数
    n = 0
    with open(INDEX, "r", encoding="utf-8") as f:
        for line in f:
            n += 1
            try:
                m = json.loads(line)
            except Exception:                                  # noqa: BLE001
                continue
            src_chunks[m.get("source", "?")] += 1

    print("总 chunk 数：%d" % n)
    print("唯一来源数：%d" % len(src_chunks))

    by_prefix = defaultdict(lambda: [0, 0, 0])   # prefix -> [来源数, 有PDF, chunk数]
    dead = []
    for src, cnt in src_chunks.items():
        prefix = src.split("/")[0]
        stem = src[:-3] if src.lower().endswith(".md") else src
        ok = (PDF_ROOT / (stem + ".pdf")).is_file()
        by_prefix[prefix][0] += 1
        by_prefix[prefix][2] += cnt
        if ok:
            by_prefix[prefix][1] += 1
        else:
            dead.append((src, cnt))

    print()
    print("%-24s %8s %8s %8s %8s %s" % ("来源前缀", "来源数", "有PDF", "死链", "chunk数", "死链率"))
    print("-" * 80)
    tot_src = tot_ok = tot_chunk = tot_dead_chunk = 0
    for p, (s, o, c) in sorted(by_prefix.items(), key=lambda kv: -kv[1][2]):
        print("%-24s %8d %8d %8d %8d %7.1f%%" % (p, s, o, s - o, c, 100.0 * (s - o) / max(s, 1)))
        tot_src += s
        tot_ok += o
        tot_chunk += c
        tot_dead_chunk += (c if o == 0 else 0)

    print("-" * 80)
    print("%-24s %8d %8d %8d %8d %7.1f%%" % ("合计", tot_src, tot_ok, tot_src - tot_ok, tot_chunk,
                                              100.0 * (tot_src - tot_ok) / max(tot_src, 1)))

    # 按 chunk 加权的死链率（检索命中的概率近似正比于 chunk 数）
    dead_chunk = sum(c for s, c in dead)
    print()
    print("按 chunk 加权（近似「被检索到的概率」）：死链 chunk %d / %d = %.1f%%"
          % (dead_chunk, tot_chunk, 100.0 * dead_chunk / max(tot_chunk, 1)))

    print()
    print("=== 死链最多的 15 条来源 ===")
    for src, cnt in sorted(dead, key=lambda kv: -kv[1])[:15]:
        print("  %5d chunks  %s" % (cnt, src))


if __name__ == "__main__":
    main()
