#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器上量化"网页导航壳"文档对检索索引的占比。

壳定义：正文 <= 1500 字 且 命中 >= 2 个导航关键词。
输出：壳文档数、其贡献的 chunk 数、占总 chunk 比例、按语料/分类分布。
"""
import json
import os
import re
from collections import Counter

BUNDLE_ROOT = os.environ.get("BUNDLE_ROOT", "/data/fagui_rag/okf_bundles")
INDEX_DIR = os.environ.get("INDEX_DIR", "/data/fagui_rag/index")
NAV = re.compile(r"当前位置|热门搜索|点击进入|标准发布|标准解读|标准文本|标准修改与解释")
MAX_LEN = 1500


def is_shell(text):
    return len(text) <= MAX_LEN and len(NAV.findall(text)) >= 2


def main():
    shells = {}
    for dp, _dn, fn in os.walk(BUNDLE_ROOT):
        for f in fn:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            try:
                t = open(p, encoding="utf-8").read()
            except Exception:
                continue
            if is_shell(t):
                shells[p] = len(t)

    # chunk 归属：chunks.jsonl 每行有 source 字段
    per_source = Counter()
    total = 0
    cj = os.path.join(INDEX_DIR, "chunks.jsonl")
    with open(cj, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                o = json.loads(line)
            except Exception:
                continue
            per_source[o.get("source") or o.get("path") or ""] += 1

    shell_chunks = sum(n for s, n in per_source.items() if s in shells)
    # 有些 source 是相对路径，做一次 basename 兜底匹配
    if shell_chunks == 0:
        bybase = {os.path.basename(p): p for p in shells}
        for s, n in per_source.items():
            if os.path.basename(s) in bybase:
                shell_chunks += n

    print(f"壳文档: {len(shells)} / 索引文档 {len([s for s in per_source if s])}")
    print(f"chunk 总数: {total}")
    print(f"壳贡献 chunk: {shell_chunks}  ({100.0*shell_chunks/max(total,1):.1f}%)")

    corp = Counter()
    for p in shells:
        rel = os.path.relpath(p, BUNDLE_ROOT)
        corp[rel.split(os.sep)[0]] += 1
    print("按语料:", dict(corp))

    top = sorted(shells.items(), key=lambda x: -x[1])[:15]
    print("\n最长的 15 份壳（字数为 md 全长）:")
    for p, n in top:
        print(f"  {n:5d} 字  {os.path.relpath(p, BUNDLE_ROOT)}")


if __name__ == "__main__":
    main()
