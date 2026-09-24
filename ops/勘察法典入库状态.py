#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""勘察《生态环境法典》在知识库里的真实状态（语料 / 索引 / 图谱 / 判据库）。

用户说"知识库缺口更新，主要是生态环境法典，这个法典是最新的"——
先量清楚：有没有、全不全、什么状态、有没有进索引与图谱，再决定补什么。

只读，不改任何文件。
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

MD_ROOT = Path(os.environ.get("MD_ROOT") or "/data/fagui_rag/okf_bundles")
IDX = Path("/data/fagui_rag/index")
CRIT = Path("/data/fagui_rag/criteria")
KG = Path("/data/eia_audit/kg_data")
NEEDLE = "生态环境法典"


def main() -> int:
    print("==== 1) 语料树里的法典文件 ====")
    hits = []
    for p in MD_ROOT.rglob("*.md"):
        if NEEDLE in p.name or NEEDLE in str(p.parent):
            hits.append(p)
    print("  命中 %d 份（按路径）" % len(hits))
    for p in hits[:20]:
        print("   · %s（%d 字节）" % (p.relative_to(MD_ROOT), p.stat().st_size))

    print("\n==== 2) 正文里提到法典的语料（不限文件名）====")
    mention = 0
    sample = []
    for p in MD_ROOT.rglob("*.md"):
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if NEEDLE in t:
            mention += 1
            if len(sample) < 8 and p not in hits:
                sample.append((p.relative_to(MD_ROOT), t.count(NEEDLE)))
    print("  正文提到法典的文件：%d 份" % mention)
    for name, n in sample:
        print("   · %s（提到 %d 次）" % (name, n))

    print("\n==== 3) 法典自身的完整性（条文数、施行日期、废止条款）====")
    for p in hits:
        if p.suffix != ".md":
            continue
        t = io.open(p, encoding="utf-8", errors="ignore").read()
        arts = re.findall(r"第[一二三四五六七八九十百千零〇]+条", t)
        nums = sorted({a for a in arts})
        last = arts[-1] if arts else None
        print("   · %s" % p.relative_to(MD_ROOT))
        print("       字数 %d；条文标记 %d 处；不同条文 %d 个；最后一处：%s"
              % (len(t), len(arts), len(nums), last))
        for kw in ("2026年8月15日", "同时废止", "第一千二百四十二条", "1242"):
            print("       含「%s」：%s" % (kw, kw in t))
        head = t[:300].replace("\n", " ")
        print("       开头：%s" % head[:200])

    print("\n==== 4) 索引里的法典块 ====")
    f = IDX / "chunks.jsonl"
    if f.is_file():
        n = 0
        with io.open(f, encoding="utf-8") as fh:
            for line in fh:
                if NEEDLE in line:
                    n += 1
        print("  索引中含「%s」的块：%d 条（总块数 %d）" % (NEEDLE, n, sum(1 for _ in io.open(f, encoding="utf-8"))))
    else:
        print("  没有 chunks.jsonl")

    print("\n==== 5) 知识图谱里有没有法典节点 ====")
    if KG.is_dir():
        for p in sorted(KG.glob("*.json"))[:12]:
            try:
                t = io.open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            print("   · %-28s %s" % (p.name, ("提到法典 %d 次" % t.count(NEEDLE)) if NEEDLE in t else "无"))
    else:
        print("  没有 kg_data 目录：%s" % KG)

    print("\n==== 6) 判据库/标准引用清单里的法典 ====")
    for p in sorted(CRIT.glob("*.json")):
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        print("   · %-34s %s" % (p.name, ("提到法典 %d 次" % t.count(NEEDLE)) if NEEDLE in t else "无"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
