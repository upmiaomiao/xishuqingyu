#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告语料样本验证：格式是否正确、检索效果是否达标、会不会淹没标准语料。

用法（服务器上，用服务 venv 以便 import numpy/retriever）：
  python3 验证环评样本.py --index /data/fagui_rag/index_eia_sample \
                          --bundle /data/fagui_rag/okf_bundles_eia_sample
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="/data/fagui_rag/index_eia_sample")
    ap.add_argument("--bundle", default="/data/fagui_rag/okf_bundles_eia_sample")
    ap.add_argument("--per-corpus-cap", type=float, default=1.0,
                    help="标准类问题里报告语料允许占的比例上限")
    a = ap.parse_args()

    meta = json.load(open(os.path.join(a.index, "meta.json"), encoding="utf-8"))
    print(f"索引 {a.index}")
    print(f"  chunks={meta.get('total_chunks')}  files={meta.get('total_files')}")

    # 语料分布 + 字段覆盖
    corpus = Counter()
    fields = Counter()
    sample_rows = []
    with open(os.path.join(a.index, "chunks.jsonl"), encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            src = o.get("source", "")
            corpus[src.split("/")[0]] += 1
            if src.startswith("环评报告"):
                for k in ("title", "type", "region", "tags"):
                    if o.get(k):
                        fields[k] += 1
                if len(sample_rows) < 3:
                    sample_rows.append(o)
    print("\n按语料 chunk 数:")
    for k, v in corpus.most_common():
        print(f"  {k}: {v}")
    print("\n报告语料字段覆盖（chunk 级）:")
    for k, v in fields.items():
        print(f"  {k}: {v}")
    for o in sample_rows:
        print(f"\n  样本 chunk: title={o.get('title','')[:40]!r} type={o.get('type')!r} "
              f"region={o.get('region')!r} tags={o.get('tags')}")
        print(f"    text: {' '.join((o.get('text') or '').split())[:160]}")

    # 检索对照
    r = Retriever(index_dir=a.index)
    print("\n===== 检索对照 =====")
    probes = [
        ("报告类问题", "郑州市金水河综合整治工程的环境影响评价结论是什么？"),
        ("标准类问题", "一般工业固体废物贮存场 I 类场的防渗要求是什么？"),
        ("标准类问题", "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？"),
        ("导则类问题", "大气环境影响评价的评价等级是怎么判定的？"),
    ]
    for label, q in probes:
        hits = r.retrieve(q, 20, 5)
        tops = [h.get("source", "").split("/")[0] for h in hits]
        rep = sum(1 for t in tops if t == "环评报告")
        print(f"\n[{label}] {q}")
        print(f"  报告语料占 {rep}/5")
        for h in hits[:3]:
            print(f"    {h.get('source','')[:88]}")
            print(f"      {' '.join((h.get('text') or '').split())[:170]}")
        if label == "标准类问题" and rep / 5 > a.per_corpus_cap:
            print(f"  ⚠️ 报告语料占比 {rep/5:.0%} 超过上限 {a.per_corpus_cap:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
